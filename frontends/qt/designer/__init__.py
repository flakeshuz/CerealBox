"""Qt Designer frontend bridge (beta).

This module provides an optional Qt-based frontend for CerealBox that can be prototyped with
Qt Designer (.ui files).

Usage:
  - If PyQt6 is installed, call cerealbox.frontends.qt.designer.start(vault_path) to launch the prototype
    that talks to the same vault via LifeAPI.
  - You can design a UI with Qt Designer and load it via the Qt loader in this module.

Note: This is a beta feature and is not the default Qt frontend.
"""
from __future__ import annotations

def available() -> bool:
    try:
        import PyQt6  # type: ignore
        return True
    except Exception:
        return False


def start(vault_path: str) -> bool:
    """Launch a minimal Qt frontend (cereal-inspired) that connects to the vault via LifeAPI.

    Returns True if the UI was started (or attempted) successfully, False otherwise.
    """
    try:
        from PyQt6 import QtWidgets  # type: ignore
        from PyQt6.QtWidgets import QApplication
    except Exception:
        print("Qt frontend not available: PyQt6 is not installed.")
        return False

    # Lazy import to avoid pulling PyQt or application modules into test environments
    try:
        from .....application import create_workspace
        from ....core.storage import Vault
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "CerealBox Unavailable", str(exc))
        return False

    app = QApplication.instance() or QApplication([])

    # Password prompt for vault open
    password, ok = QtWidgets.QInputDialog.getText(None, "Vault Password", "Enter vault password:", QtWidgets.QLineEdit.EchoMode.Password)
    if not ok:
        return False

    try:
        vault = Vault.create(vault_path, password) if not Vault.exists(vault_path) else Vault.open(vault_path, password)
        api = create_workspace(vault)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "Open Vault Failed", str(exc))
        return False

    # Main window scaffold (placeholder for designer-driven UI)
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("CerealBox — Qt Frontend")
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    header = QtWidgets.QLabel("CerealBox Qt Frontend - Beta")
    header.setStyleSheet("font-size: 20px; font-weight: bold;")
    layout.addWidget(header)

    # Quick module list snapshot
    mod_list = QtWidgets.QListWidget()
    for m in api.modules.values():
        if m.show_in_navigation:
            mod_list.addItem(m.title)
    layout.addWidget(mod_list)

    window.setCentralWidget(central)
    window.resize(900, 600)
    window.show()
    app.exec()

    return True
