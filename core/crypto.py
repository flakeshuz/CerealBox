"""Password-based encryption: scrypt key derivation + AES-256-GCM (authenticated)."""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

SCRYPT_DEFAULTS = {"n": 2**16, "r": 8, "p": 1}  # ~64 MB, a few hundred ms per unlock
KEY_LEN, NONCE_LEN, SALT_LEN = 32, 12, 16


class WrongPasswordOrCorrupt(Exception):
    """GCM authentication failed: bad password, or the data was altered/damaged."""


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def derive_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=KEY_LEN, n=n, r=r, p=p).derive(password.encode("utf-8"))


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)  # fresh random nonce on every save
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < NONCE_LEN + 16:
        raise WrongPasswordOrCorrupt("Vault data is truncated.")
    try:
        return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)
    except InvalidTag as exc:
        raise WrongPasswordOrCorrupt("Wrong password, or the vault was modified.") from exc
