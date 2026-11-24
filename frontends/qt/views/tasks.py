"""Tasks screen: filtered list, quick complete, search, repeat, and reminders."""
from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import QItemSelectionModel, Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from ....core import dates as D
from ....core.rrule import FREQ_BY_LABEL as FREQ
from ....core.rrule import LABEL_BY_FREQ as CHOICE_OF_FREQ
from ....core.rrule import REPEAT_CHOICES, REPEAT_NONE, WEEKDAY_CODES, build_rrule, parse_rrule
from ....core.rrule import REPEAT_CUSTOM as CUSTOM
from CerealBox.frontends.qt import theme as T
from CerealBox.modules.tasks import is_overdue
from CerealBox.modules.tasks.models import PRIORITY_CODES, PRIORITY_NAMES, Task

VIEW_LABELS = (("open", "Open"), ("today", "Today"), ("done", "Done"), ("all", "All"))


def fmt_due(t: Task, now: datetime) -> str:
    if not t.due:
        return ""
    d = t.due.date()
    day = {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get((d - now.date()).days) or f"{d:%a %b} {d.day}"
    return f"{day} {D.fmt_time(t.due)}" if t.has_time else day


def _show(dlg: QDialog, parent: QWidget) -> None:
    dlg.setModal(True)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


class TasksView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        self.view = "open"
        self._ids = []
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        root.addLayout(bar)
        title = QLabel("Tasks")
        title.setStyleSheet("font-size: 19px; font-weight: 600")
        bar.addWidget(title)
        group = QButtonGroup(self)
        self.view_buttons = {}
        for key, label in VIEW_LABELS:
            button = QRadioButton(label)
            button.setChecked(key == self.view)
            button.toggled.connect(lambda checked, k=key: self._set_view(k) if checked else None)
            group.addButton(button)
            bar.addWidget(button)
            self.view_buttons[key] = button
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks and tags")
        self.search.setMaximumWidth(230)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search)
        bar.addStretch(1)
        new_button = self._button(bar, "New task", self.new)
        new_button.setProperty("primary", True)

        actions = QHBoxLayout()
        root.addLayout(actions)
        self.toggle_btn = self._button(actions, "Complete", self.toggle_selected)
        self.edit_btn = self._button(actions, "Edit", self.edit_selected)
        self.delete_btn = self._button(actions, "Delete", self.delete_selected)
        actions.addStretch(1)
        self.status = QLabel()
        actions.addWidget(self.status)
        self.schedule = QLabel()
        self.schedule.setWordWrap(True)
        root.addWidget(self.schedule)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Task", "Due", "Priority", "Tags"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 44)
        self.table.setColumnWidth(1, 360)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(3, 90)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        self.table.itemActivated.connect(lambda *_: self.edit_selected())
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)
        root.addWidget(self.table, 1)
        self._shortcuts = []
        for sequence, callback, owner in (("Ctrl+N", self.new, self), ("Space", self.toggle_selected, self.table),
                                          ("Return", self.edit_selected, self.table),
                                          ("Delete", self.delete_selected, self.table),
                                          ("Backspace", self.delete_selected, self.table)):
            shortcut = QShortcut(QKeySequence(sequence), owner)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut if owner is self
                                else Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self._subs = [("tasks.*", self._on_change), ("calendar.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(60_000)
        self.destroyed.connect(self._cleanup)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.refresh()

    @staticmethod
    def _button(layout, text, callback):
        b = QPushButton(text)
        b.clicked.connect(callback)
        layout.addWidget(b)
        return b

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle_selected()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.edit_selected()
        elif event.key() == Qt.Key.Key_N and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.new()
        else:
            super().keyPressEvent(event)

    def _set_view(self, view):
        self.view = view
        self.refresh()

    def _on_change(self, *_args, **_kwargs):
        self.refresh()

    def _cleanup(self, *_args):
        for pattern, handler in self._subs:
            self.mod.api.off(pattern, handler)

    def refresh(self, *_args):
        now = D.now()
        tasks = self.mod.list(self.view, self.search.text(), now)
        self._ids = [task.id for task in tasks]
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = ("✓" if task.done else "○", task.title + ("  ↻" if task.rrule else ""),
                      fmt_due(task, now), PRIORITY_NAMES[task.priority], ", ".join(task.tags))
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                if task.done:
                    item.setForeground(QColor(T.FAINT))
                elif is_overdue(task, now):
                    item.setForeground(QColor(T.NOW))
                self.table.setItem(row, col, item)
        open_now = self.mod.list("open", "", now)
        overdue = sum(is_overdue(task, now) for task in open_now)
        if self.view == "today":
            count, label = len(self.mod.list("today", "", now)), "to do today or earlier"
        else:
            count, label = len(open_now), "open"
        self.status.setText(f"{count} {label}" + (f"  ·  {overdue} overdue" if overdue else ""))
        self._refresh_schedule(now)
        self._update_buttons()
        self.empty.setText(self._empty_text() if not tasks else "")
        self.empty.setVisible(not tasks)

    def theme_changed(self) -> None:
        selected = set(self._selected())
        self.refresh()
        self.table.clearSelection()
        for row, task_id in enumerate(self._ids):
            if task_id in selected:
                self.table.selectionModel().select(
                    self.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )

    def _empty_text(self):
        if self.search.text().strip():
            return f"No tasks match “{self.search.text().strip()}”."
        return {"open": "Nothing open. Enjoy the quiet.", "today": "Nothing due today.",
                "done": "Nothing finished yet.", "all": "No tasks yet. Press Ctrl+N to add one."}[self.view]

    def _refresh_schedule(self, now):
        if self.view != "today" or not self.mod.api.has_service("calendar.events_between"):
            self.schedule.clear()
            return
        day = D.day_start(now.date())
        rows = self.mod.api.call("calendar.events_between", day, day + timedelta(days=1))
        if not rows:
            self.schedule.setText("Nothing on the calendar today.")
            return
        lines = [f"{'All day' if r['all_day'] else D.fmt_time(r['start'])}   {r['title']}" for r in rows[:5]]
        if len(rows) > 5:
            lines.append(f"+{len(rows)-5} more")
        self.schedule.setText("On the calendar today:\n" + "\n".join(lines))

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._ids[row] for row in rows if row < len(self._ids)]

    def _update_buttons(self):
        selected = self._selected()
        self.edit_btn.setEnabled(len(selected) == 1)
        self.toggle_btn.setEnabled(bool(selected))
        task = self.mod.get(selected[0]) if len(selected) == 1 else None
        self.toggle_btn.setText("Reopen" if task and task.done else "Complete")
        self.delete_btn.setEnabled(bool(selected))

    def new(self):
        TaskDialog(self, self.mod)

    def edit_selected(self):
        selected = self._selected()
        if len(selected) == 1:
            task = self.mod.get(selected[0])
            if task:
                TaskDialog(self, self.mod, task)

    def toggle_selected(self):
        for task_id in self._selected():
            self.mod.toggle(task_id)

    def delete_selected(self):
        selected = self._selected()
        if selected and QMessageBox.question(self, "Delete", "Delete this task?" if len(selected) == 1
                                              else f"Delete {len(selected)} tasks?") == QMessageBox.StandardButton.Yes:
            for task_id in selected:
                self.mod.delete(task_id)


class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, mod, task: Task | None = None):
        super().__init__(parent)
        self.mod, self.task = mod, task
        self.setWindowTitle("Edit task" if task else "New task")
        self.setModal(True)
        t = task
        self.title_entry = QLineEdit(t.title if t else "")
        self.date = QLineEdit(f"{t.due.month}/{t.due.day}/{t.due.year}" if t and t.due else "")
        self.clock = QLineEdit(D.fmt_time(t.due) if t and t.has_time else "")
        self.priority = QComboBox()
        self.priority.addItems(list(PRIORITY_CODES))
        self.priority.setCurrentText(PRIORITY_NAMES[t.priority if t else 2])
        self.tags = QLineEdit(", ".join(t.tags) if t else "")
        self.reminders = QLineEdit(", ".join(D.compact_minutes(m) for m in t.reminders) if t else "")
        self.repeat = QComboBox()
        self.loaded_repeat = REPEAT_NONE
        if t and t.rrule:
            parsed = parse_rrule(t.rrule)
            self.loaded_repeat = CUSTOM if parsed.custom else CHOICE_OF_FREQ.get(parsed.freq, REPEAT_NONE)
        self.repeat.addItems(REPEAT_CHOICES + ([CUSTOM] if self.loaded_repeat == CUSTOM else []))
        self.repeat.setCurrentText(self.loaded_repeat)
        self.notes = QTextEdit(t.notes if t else "")
        self.notes.setFixedHeight(90)
        form = QFormLayout()
        form.addRow("Task", self.title_entry)
        date_time = QWidget()
        date_row = QHBoxLayout(date_time)
        date_row.setContentsMargins(0, 0, 0, 0)
        date_row.addWidget(self.date)
        date_row.addWidget(self.clock)
        form.addRow("Due date and time", date_time)
        form.addRow("Repeat", self.repeat)
        form.addRow("Priority", self.priority)
        form.addRow("Tags", self.tags)
        form.addRow("Reminders", self.reminders)
        form.addRow("", QLabel("needs a time, e.g. 15, 1h"))
        form.addRow("Notes", self.notes)
        root = QVBoxLayout(self)
        root.addLayout(form)
        buttons = QDialogButtonBox()
        save = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        save.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._save)
        self.title_entry.returnPressed.connect(self._save)
        self._show(parent)

    def _show(self, parent):
        _show(self, parent)
        self.title_entry.setFocus()

    def _collect(self) -> dict:
        title = self.title_entry.text().strip()
        if not title:
            raise ValueError("Give the task a name.")
        dstr, tstr = self.date.text().strip(), self.clock.text().strip()
        has_time, due = False, None
        if dstr:
            d = D.parse_date(dstr)
            if tstr:
                due, has_time = datetime.combine(d, D.parse_time(tstr)), True
            else:
                due = D.day_start(d)
        elif tstr:
            raise ValueError("Add a due date as well as a time.")
        reminders = D.parse_minute_list(self.reminders.text()) if self.reminders.text().strip() else []
        if reminders and not has_time:
            raise ValueError("Reminders need a due time.")
        rep = self.repeat.currentText()
        rrule = None
        if rep != REPEAT_NONE:
            if due is None:
                raise ValueError("A repeating task needs a due date.")
            if rep == CUSTOM:
                rrule = self.task.rrule
            elif rep == self.loaded_repeat and self.task and self.task.rrule and (
                    self.task.due is None or self.task.due.weekday() == due.weekday()):
                rrule = self.task.rrule
            else:
                keep = parse_rrule(self.task.rrule) if self.task and self.task.rrule else None
                byday = [WEEKDAY_CODES[due.weekday()]] if rep == "Weekly" else []
                rrule = build_rrule(FREQ[rep], interval=keep.interval if keep else 1, byday=byday,
                                    count=keep.count if keep else None, until=keep.until if keep else None)
        return {"title": title, "due": due, "has_time": has_time, "rrule": rrule, "reminders": reminders,
                "priority": PRIORITY_CODES[self.priority.currentText()],
                "tags": [x.strip() for x in self.tags.text().split(",") if x.strip()],
                "notes": self.notes.toPlainText().strip()}

    def _save(self):
        try:
            data = self._collect()
        except ValueError as exc:
            QMessageBox.critical(self, "Check the task", str(exc))
            return
        task = self.task.copy() if self.task else Task.new(data["title"])
        if self.task is None or data["due"] != task.due:
            task.series_start = data["due"] if data["rrule"] else None
        for key, value in data.items():
            setattr(task, key, value)
        self.mod.save(task)
        self.accept()
