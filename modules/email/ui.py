"""Email UI scaffold"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class EmailView(QWidget):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod

        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Email"))
        heading.addStretch()
        receive_button = QPushButton("Receive sample")
        receive_button.clicked.connect(self._receive_sample)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        heading.addWidget(receive_button)
        heading.addWidget(refresh_button)
        layout.addLayout(heading)

        self.listbox = QListWidget()
        layout.addWidget(self.listbox)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        for email in (self.mod.list_inbox() or []):
            subject = email.get("subject", "No subject")
            status = "Read" if email.get("read") else "Unread"
            self.listbox.addItem(f"{subject} — {status}")

    def _receive_sample(self):
        self.mod.receive_email(
            "bot@example.com", "me@example.com", "Sample", "Body of sample email"
        )
        self.refresh()
