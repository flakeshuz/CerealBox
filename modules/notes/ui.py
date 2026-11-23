"""Notes PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


class NotesView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Notes")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("Add Note")
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.listbox = QListWidget()
        root.addWidget(self.listbox)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        for n in (self.mod.list_notes() or []):
            self.listbox.addItem(n.get("title", "Untitled"))

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Note")
        layout = QVBoxLayout(dlg)
        title = QLineEdit()
        content = QTextEdit()
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        layout.addWidget(QLabel("Content"))
        layout.addWidget(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if value:
                self.mod.add_note(value, content.toPlainText())
                self.refresh()
