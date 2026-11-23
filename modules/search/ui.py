"""Search UI scaffold"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SearchView(QWidget):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod

        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Search"))
        heading.addStretch()
        self.btn = QPushButton("Search")
        self.btn.clicked.connect(self.run)
        heading.addWidget(self.btn)
        layout.addLayout(heading)

        self.entry = QLineEdit(self)
        self.entry.returnPressed.connect(self.run)
        layout.addWidget(self.entry)
        self.results = QListWidget()
        layout.addWidget(self.results)

    def run(self):
        term = self.entry.text()
        results = self.mod.global_search(term)
        self.results.clear()
        for result in (results or []):
            self.results.addItem(str(result))
