"""Qt password dialogs for opening, creating, and changing a vault."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..core import Vault, VaultError, WrongPassword
from . import theme as T

MIN_LENGTH = 8


class PasswordDialog(QDialog):
    """After exec(), `.password` contains the accepted password or None."""

    def __init__(self, parent: QWidget, mode: str, path: Path | None = None, error: str = ""):
        super().__init__(parent)
        self.password: str | None = None
        self.mode = mode
        titles = {"unlock": "Unlock CerealBox", "create": "Create your CerealBox", "change": "Change password"}
        self.setWindowTitle(titles[mode])
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        title = QLabel(titles[mode])
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        blurb = {
            "unlock": f"Enter your password to open {path.name if path else 'your vault'}.",
            "create": "Choose a password to protect your vault. There is no recovery if you forget it.",
            "change": "Choose a new password for this vault.",
        }[mode]
        explanation = QLabel(blurb)
        explanation.setWordWrap(True)
        explanation.setObjectName("muted")
        layout.addWidget(explanation)

        self.e1 = QLineEdit(self)
        self.e1.setPlaceholderText("Password" if mode == "unlock" else "New password")
        self.e1.setEchoMode(QLineEdit.EchoMode.Password)
        self.e1.setAccessibleName("Password")
        layout.addWidget(self.e1)
        self.e2: QLineEdit | None = None
        if mode != "unlock":
            self.e2 = QLineEdit(self)
            self.e2.setPlaceholderText("Confirm password")
            self.e2.setEchoMode(QLineEdit.EchoMode.Password)
            self.e2.setAccessibleName("Confirm password")
            layout.addWidget(self.e2)
            self.e2.returnPressed.connect(self._ok)
        else:
            self.e1.returnPressed.connect(self._ok)

        reveal = QCheckBox("Show passwords")
        reveal.toggled.connect(
            lambda visible: [
                field.setEchoMode(QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
                for field in (self.e1, self.e2)
                if field is not None
            ]
        )
        layout.addWidget(reveal)

        self.msg = QLabel(error)
        self.msg.setStyleSheet(f"color: {T.NOW};")
        self.msg.setWordWrap(True)
        layout.addWidget(self.msg)
        buttons = QDialogButtonBox()
        buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        submit = buttons.addButton(
            {"unlock": "Unlock", "create": "Create vault", "change": "Change password"}[mode],
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        submit.setProperty("primary", True)
        submit.style().unpolish(submit)
        submit.style().polish(submit)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._ok)
        layout.addWidget(buttons)
        T.center(self, parent)
        self.e1.setFocus(Qt.FocusReason.OtherFocusReason)

    def _ok(self) -> None:
        password = self.e1.text()
        if self.mode != "unlock":
            if len(password) < MIN_LENGTH:
                self.msg.setText(f"Use at least {MIN_LENGTH} characters.")
                self.e1.setFocus()
                return
            if self.e2 is None or password != self.e2.text():
                self.msg.setText("The two passwords don't match.")
                self.e2.setFocus()
                return
        elif not password:
            self.msg.setText("Enter your password.")
            self.e1.setFocus()
            return
        self.password = password
        self.accept()


def unlock_vault(root: QWidget, path: Path) -> Vault | None:
    """Create or open the vault at `path`. None means the user cancelled."""
    creating = not Vault.exists(path)
    error = ""
    while True:
        dialog = PasswordDialog(root, "create" if creating else "unlock", path, error)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.password is None:
            return None
        try:
            return Vault.create(path, dialog.password) if creating else Vault.open(path, dialog.password)
        except WrongPassword:
            error = "That password didn't work. Check it and try again."
        except (VaultError, OSError, ValueError) as exc:
            QMessageBox.critical(root, "Can't open vault", str(exc))
            return None


def ask_new_password(root: QWidget) -> str | None:
    dialog = PasswordDialog(root, "change")
    return dialog.password if dialog.exec() == QDialog.DialogCode.Accepted else None
