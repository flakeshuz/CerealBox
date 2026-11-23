"""Desktop launcher for CerealBox."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required.", file=sys.stderr)
        raise SystemExit(1)
    sys.path.insert(0, str(root.parent))

    from CerealBox.app import main as package_main

    try:
        raise SystemExit(package_main())
    except ModuleNotFoundError as exc:
        if exc.name not in {"cryptography", "PyQt6"}:
            raise
        print("Installing CerealBox dependencies...", file=sys.stderr)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--user", "--disable-pip-version-check", "."],
            cwd=root,
            check=True,
        )
        raise SystemExit(package_main())
