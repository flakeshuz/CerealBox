"""Contacts PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
)


class ContactsView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Contacts")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        birthdays = QPushButton("Birthdays")
        birthdays.clicked.connect(self.toggle_birthdays)
        header.addWidget(birthdays)
        add = QPushButton("Add Contact")
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.birthdays_visible = False
        self.birthdays_frame = QWidget()
        birthdays_layout = QVBoxLayout(self.birthdays_frame)
        birthdays_layout.addWidget(QLabel("Birthdays this year:"))
        self.birthdays_list = QListWidget()
        birthdays_layout.addWidget(self.birthdays_list)
        root.addWidget(self.birthdays_frame)
        self.birthdays_frame.hide()
        self.listbox = QListWidget()
        root.addWidget(self.listbox)
        self.refresh()

    def toggle_birthdays(self):
        self.birthdays_visible = not self.birthdays_visible
        self.birthdays_frame.setVisible(self.birthdays_visible)
        if self.birthdays_visible:
            self._refresh_birthdays()

    def _refresh_birthdays(self):
        self.birthdays_list.clear()
        for b in (self.mod.birthdays_entries() or []):
            self.birthdays_list.addItem(f"{b.get('name', '')} - {b.get('birthday', '')}")

    def refresh(self):
        self.listbox.clear()
        for c in (self.mod.list_contacts() or []):
            self.listbox.addItem(c.get("name", "Unknown"))
        self._refresh_birthdays()

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Contact")
        layout = QVBoxLayout(dlg)
        name = QLineEdit()
        layout.addWidget(QLabel("Name"))
        layout.addWidget(name)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = name.text().strip()
            if value:
                self.mod.add_contact(value)
                self.refresh()
