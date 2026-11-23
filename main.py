"""Desktop launcher for CerealBox."""
from __future__ import annotations

import sys
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root.parent))

    from CerealBox.app import main as package_main

    raise SystemExit(package_main())
