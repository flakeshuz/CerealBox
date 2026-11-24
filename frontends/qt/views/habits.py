"""Habits PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
)


class HabitsView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Habits")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        self.checkin_btn = QPushButton("Check-in")
        self.checkin_btn.clicked.connect(self.check_in_selected)
        header.addWidget(self.checkin_btn)
        add = QPushButton("Add Habit")
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.listbox = QListWidget()
        self.listbox.currentRowChanged.connect(lambda _row: self._refresh_checkins())
        root.addWidget(self.listbox)
        checkins = QWidget()
        check_layout = QVBoxLayout(checkins)
        check_layout.addWidget(QLabel("Recent check-ins:"))
        self.checkins_list = QListWidget()
        check_layout.addWidget(self.checkins_list)
        root.addWidget(checkins)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        self._habits = self.mod.list_habits() or []
        for h in self._habits:
            self.listbox.addItem(h.get("title", "Habit"))
        self._refresh_checkins()

    def _selected_habit_id(self):
        row = self.listbox.currentRow()
        if row < 0 or row >= len(getattr(self, "_habits", [])):
            return None
        return self._habits[row]["id"]

    def _refresh_checkins(self):
        self.checkins_list.clear()
        hid = self._selected_habit_id()
        if not hid:
            return
        for c in (self.mod.list_checkins(hid) or []):
            self.checkins_list.addItem(c.get("date", ""))

    def check_in_selected(self):
        hid = self._selected_habit_id()
        if not hid:
            return
        self.mod.check_in(hid)
        self._refresh_checkins()
        self.refresh()

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Habit")
        layout = QVBoxLayout(dlg)
        title = QLineEdit()
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if value:
                self.mod.add_habit(value)
                self.refresh()
