"""Passwords UI scaffold"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PasswordsView(QWidget):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod

        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Passwords"))
        heading.addStretch()
        store_button = QPushButton("Store")
        store_button.clicked.connect(self.store)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        heading.addWidget(store_button)
        heading.addWidget(refresh_button)
        layout.addLayout(heading)

        self.listbox = QListWidget()
        layout.addWidget(self.listbox)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        for credential in (self.mod.list_credentials() or []):
            # Show only the credential key; never expose its value in the list.
            self.listbox.addItem(credential.get("key", "secret"))

    def store(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Store Credential")
        form = QFormLayout(dialog)
        key_input = QLineEdit(dialog)
        value_input = QLineEdit(dialog)
        form.addRow("Key", key_input)
        form.addRow("Value", value_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key = key_input.text()
            if key:
                self.mod.store_credential(key, value_input.text())
                self.refresh()
