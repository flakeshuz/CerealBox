"""Entry point: python main.py [--vault PATH]"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def default_vault_path() -> Path:
    base = os.environ.get("CEREALBOX_HOME")
    return (Path(base) if base else Path.home() / ".cerealbox") / "vault.cerealbox"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cerealbox", description="Fresh, local, encrypted life management.")
    parser.add_argument("--vault", type=Path, default=None, help=f"vault file (default: {default_vault_path()})")
    args = parser.parse_args(argv)

    from .ui.shell import Shell  # imported here so --help works without a display

    shell = Shell(args.vault or default_vault_path())
    if shell.start():
        shell.mainloop()
