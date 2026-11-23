"""Qt Designer frontend bridge (beta).

This module provides an optional Qt-based frontend for LifeOS that can be prototyped with
Qt Designer (.ui files). It is intentionally optional and lazy-loaded so the Tkinter-based
UI remains the default/backward-compatible UI for tests.

Usage:
  - If PyQt6 is installed, call lifeos.ui.qt_designer.start(vault_path) to launch a Qt frontend
    that talks to the same vault via LifeAPI.
  - You can design a UI with Qt Designer and load it via the Qt loader in this module.

Note: This is a beta feature. It should not affect the existing tests since the function is
only invoked when explicitly started.
"""
from __future__ import annotations

from pathlib import Path


def available() -> bool:
    try:
        import PyQt6  # type: ignore
        return True
    except Exception:
        return False


def start(vault_path: str) -> bool:
    """Launch a minimal Qt frontend (Apple-inspired) that connects to the vault via LifeAPI.

    Returns True if the UI was started (or attempted) successfully, False otherwise.
    """
    try:
        from PyQt6 import QtWidgets  # type: ignore
        from PyQt6.QtWidgets import QApplication
    except Exception:
        print("Qt frontend not available: PyQt6 is not installed.")
        return False

    # Lazy import to avoid pulling PyQt into test environments
    try:
        from lifeos.core.storage import Vault  # type: ignore
        from lifeos.core.api import LifeAPI  # type: ignore
        from lifeos.modules import default_modules  # type: ignore
        vault = Vault.open(vault_path, "") if Path(vault_path).exists() else None  # password will be requested below
    except Exception:
        vault = None

    app = QApplication([])

    # Password prompt for vault open
    password, ok = QtWidgets.QInputDialog.getText(None, "Vault Password", "Enter vault password:", QtWidgets.QLineEdit.EchoMode.Password)
    if not ok:
        return False

    try:
        vault = Vault.open(vault_path, password)
        api = LifeAPI(vault)
        for module in default_modules():
            api.register(module)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "Open Vault Failed", str(exc))
        return False

    # Main window scaffold (placeholder for designer-driven UI)
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("LifeOS — Qt Frontend (Apple-inspired)")
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    header = QtWidgets.QLabel("LifeOS Qt Frontend (Apple-inspired) - Beta")
    header.setStyleSheet("font-size: 20px; font-weight: bold;")
    layout.addWidget(header)

    # Quick module list snapshot
    mod_list = QtWidgets.QListWidget()
    for m in api.modules.values():
        mod_list.addItem(m.title)
    layout.addWidget(mod_list)

    window.setCentralWidget(central)
    window.resize(900, 600)
    window.show()
    app.exec()

    return True
