"""CerealBox application entry point."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cerealbox", description="Fresh, local, encrypted life management.")
    parser.add_argument("--vault", type=Path, default=None, help=f"vault file (default: {default_vault_path()})")
    args = parser.parse_args(argv)

    from .ui.shell import Shell  # imported here so --help works without a display

    shell = Shell(args.vault or default_vault_path())
    if shell.start():
        shell.mainloop()
