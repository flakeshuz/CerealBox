"""Goals PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
)


class GoalsView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Goals")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("Add Goal")
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.listbox = QListWidget()
        root.addWidget(self.listbox)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        for g in (self.mod.list_goals() or []):
            self.listbox.addItem(g.get("title", "Goal"))

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Goal")
        layout = QVBoxLayout(dlg)
        title = QLineEdit()
        target = QLineEdit()
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        layout.addWidget(QLabel("Target"))
        layout.addWidget(target)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if value:
                self.mod.add_goal(value, target.text().strip())
                self.refresh()
