"""Qt desktop frontend entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def run(vault_path: Path) -> int:
    from PyQt6.QtWidgets import QApplication

    from . import theme
    from .shell import Shell

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("CerealBox")
    app.setOrganizationName("CerealBox")
    theme.apply(app)
    shell = Shell(vault_path)
    if not shell.start():
        return 0
    shell.show()
    return app.exec()
