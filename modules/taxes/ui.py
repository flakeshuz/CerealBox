"""Taxes UI scaffold"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTreeWidget, QVBoxLayout, QWidget


class TaxesView(QWidget):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Taxes"))
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Category", "Rate"])
        layout.addWidget(self.tree)
