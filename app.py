"""CerealBox application entry point."""
from __future__ import annotations

import argparse
from importlib import import_module, metadata
import os
from pathlib import Path

from .frontends import Frontend


def default_vault_path() -> Path:
    base = os.environ.get("CEREALBOX_HOME")
    if base:
        vault_dir = Path(base)
    elif os.name == "nt":
        appdata = os.environ.get("APPDATA")
        vault_dir = Path(appdata) / "CerealBox" if appdata else Path.home() / "AppData" / "Roaming" / "CerealBox"
    else:
        vault_dir = Path.home() / ".cerealbox"
    return vault_dir / "vault.cerealbox"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cerealbox", description="Fresh, local, encrypted life management.")
    parser.add_argument("--vault", type=Path, default=None, help=f"vault file (default: {default_vault_path()})")
    parser.add_argument("--frontend", default="qt", help="frontend to run (default: qt)")
    args = parser.parse_args(argv)

    frontend = _load_frontend(args.frontend)
    return frontend(args.vault or default_vault_path())


def _load_frontend(name: str) -> Frontend:
    entrypoints = {
        entry.name: entry
        for entry in metadata.entry_points(group="cerealbox.frontends")
    }
    if name in entrypoints:
        try:
            return entrypoints[name].load()
        except ModuleNotFoundError as exc:
            if exc.name == "PyQt6":
                raise RuntimeError(
                    "The Qt frontend requires the desktop extra. Install CerealBox with `pip install '.[desktop]'`."
                ) from exc
            raise

    if name == "qt":
        try:
            return import_module(".frontends.qt.app", __package__).run
        except ModuleNotFoundError as exc:
            if exc.name == "PyQt6":
                raise RuntimeError(
                    "The Qt frontend requires the desktop extra. Install CerealBox with `pip install '.[desktop]'`."
                ) from exc
            raise

    available = ", ".join(sorted({"qt", *entrypoints})) or "none"
    raise ValueError(f"Unknown frontend {name!r}. Available frontends: {available}.")
