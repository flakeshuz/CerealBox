"""Home PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
)


class HomeView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Home")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("Add maintenance")
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.listbox = QListWidget()
        root.addWidget(self.listbox)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        for m in (self.mod.list_maintenance() or []):
            self.listbox.addItem(m.get("title", "Maintenance"))

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add maintenance")
        layout = QVBoxLayout(dlg)
        title = QLineEdit()
        due = QLineEdit()
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        layout.addWidget(QLabel("Due"))
        layout.addWidget(due)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if value:
                self.mod.add_maintenance(value, due.text().strip())
                self.refresh()
