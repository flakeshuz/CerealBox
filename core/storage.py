"""The vault: ONE encrypted file holding every module's data.

File layout:  MAGIC | header_len (4 bytes) | header JSON (kdf params + salt) | nonce | ciphertext
The header is authenticated (used as AES-GCM associated data), so tampering with the KDF
settings is detected. The payload is zlib-compressed JSON:
    {"schema": 1, "collections": {"calendar.events": {"<id>": {...}, ...}, ...}}
Saves are atomic (write temp file, fsync, rename) and keep the previous version as .bak.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import zlib
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from . import crypto

MAGIC = b"LIFEOS01"
SCHEMA = 1
EXPORT_FORMAT = "lifeos-export"


class VaultError(Exception):
    pass


class WrongPassword(VaultError):
    pass


class Vault:
    def __init__(self, path: Path, key: bytes, kdf: dict, data: dict):
        self.path, self._key, self._kdf, self._data = Path(path), key, kdf, data
        self._depth = 0
        self._dirty = False

    # ---- open / create ---------------------------------------------------------------
    @staticmethod
    def exists(path: str | Path) -> bool:
        return Path(path).is_file()

    @classmethod
    def create(cls, path: str | Path, password: str) -> Vault:
        path = Path(path)
        if path.exists():
            raise VaultError(f"{path} already exists.")
        path.parent.mkdir(parents=True, exist_ok=True)
        kdf = {"kdf": "scrypt", **crypto.SCRYPT_DEFAULTS, "salt": _b64(crypto.new_salt())}
        vault = cls(path, _derive(password, kdf), kdf, {"schema": SCHEMA, "collections": {}})
        vault.save()
        return vault

    @classmethod
    def open(cls, path: str | Path, password: str) -> Vault:
        path = Path(path)
        raw = path.read_bytes()
        if raw[:8] != MAGIC:
            raise VaultError(f"{path} is not a LifeOS vault.")
        hlen = int.from_bytes(raw[8:12], "big")
        head = raw[: 12 + hlen]
        kdf = json.loads(raw[12 : 12 + hlen])
        key = _derive(password, kdf)
        try:
            plain = crypto.decrypt(key, raw[12 + hlen :], head)
        except crypto.WrongPasswordOrCorrupt as exc:
            raise WrongPassword(str(exc)) from exc
        data = json.loads(zlib.decompress(plain))
        data.setdefault("collections", {})
        return cls(path, key, kdf, data)

    # ---- persistence -----------------------------------------------------------------
    def _serialize(self) -> bytes:
        header = json.dumps(self._kdf, separators=(",", ":")).encode()
        head = MAGIC + len(header).to_bytes(4, "big") + header
        plain = zlib.compress(json.dumps(self._data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        return head + crypto.encrypt(self._key, plain, head)

    def save(self) -> None:
        if self._depth:
            self._dirty = True
            return
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "wb") as fh:
            fh.write(self._serialize())
            fh.flush()
            os.fsync(fh.fileno())
        with suppress(OSError):
            os.chmod(tmp, 0o600)
        if self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".bak"))
        os.replace(tmp, self.path)

    @contextmanager
    def batch(self) -> Iterator[Vault]:
        """Group many writes into one save. If anything raises, all changes are rolled back."""
        outer = self._depth == 0
        snapshot = copy.deepcopy(self._data) if outer else None
        self._depth += 1
        try:
            yield self
        except BaseException:
            if outer:
                self._data, self._dirty = snapshot, False
            raise
        finally:
            self._depth -= 1
        if outer and self._dirty:
            self._dirty = False
            self.save()

    def change_password(self, new_password: str) -> None:
        self._kdf = {**self._kdf, "salt": _b64(crypto.new_salt())}
        self._key = _derive(new_password, self._kdf)
        self.save()

    def backup_to(self, dest: str | Path) -> None:
        """Copy the (still encrypted) vault file."""
        shutil.copy2(self.path, dest)

    # ---- records ---------------------------------------------------------------------
    def get(self, collection: str, key: str) -> dict | None:
        return copy.deepcopy(self._data["collections"].get(collection, {}).get(key))

    def put(self, collection: str, key: str, record: dict) -> None:
        rec = json.loads(json.dumps(record))  # fails fast on non-JSON data
        self._data["collections"].setdefault(collection, {})[key] = rec
        self.save()

    def delete(self, collection: str, key: str) -> bool:
        removed = self._data["collections"].get(collection, {}).pop(key, None) is not None
        if removed:
            self.save()
        return removed

    def all(self, collection: str) -> list[dict]:
        return copy.deepcopy(list(self._data["collections"].get(collection, {}).values()))

    def collections(self) -> list[str]:
        return sorted(self._data["collections"])

    # ---- import / export (plain JSON, no lock-in) --------------------------------------
    def export_data(self) -> dict[str, Any]:
        return {
            "format": EXPORT_FORMAT,
            "schema": SCHEMA,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "collections": copy.deepcopy(self._data["collections"]),
        }

    def import_data(self, payload: dict, replace: bool = False) -> None:
        if payload.get("format") != EXPORT_FORMAT or "collections" not in payload:
            raise VaultError("That file is not a LifeOS export.")
        with self.batch():
            if replace:
                self._data["collections"] = {}
            for name, records in payload["collections"].items():
                self._data["collections"].setdefault(name, {}).update(copy.deepcopy(records))
            self._dirty = True


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _derive(password: str, kdf: dict) -> bytes:
    return crypto.derive_key(password, base64.b64decode(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
