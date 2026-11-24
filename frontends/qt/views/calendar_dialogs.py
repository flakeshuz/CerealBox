"""Dialogs for calendar events, categories, and linked-event details."""
from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from ....core import dates as D
from ....core.ids import new_id
from CerealBox.modules.calendar.models import DEFAULT_COLOR, IMPORT_PALETTE, Category, Event, Occurrence
from CerealBox.modules.calendar.recurrence import WEEKDAY_CODES, build_rrule, describe_rrule, parse_rrule

NO_REPEAT, CUSTOM = "Does not repeat", "Custom (keep imported rule)"
REPEAT_CHOICES = [NO_REPEAT, "Daily", "Weekly", "Monthly", "Yearly"]
FREQ_OF = {"Daily": "DAILY", "Weekly": "WEEKLY", "Monthly": "MONTHLY", "Yearly": "YEARLY"}
CHOICE_OF = {v: k for k, v in FREQ_OF.items()}
UNIT_OF = {"Daily": "day(s)", "Weekly": "week(s)", "Monthly": "month(s)", "Yearly": "year(s)"}
WEEK_ORDER = [("SU", "Su"), ("MO", "Mo"), ("TU", "Tu"), ("WE", "We"), ("TH", "Th"), ("FR", "Fr"), ("SA", "Sa")]
NO_CATEGORY = "No category"


def _date_text(d: datetime) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def _compact_minutes(m: int) -> str:
    if m and m % 1440 == 0:
        return f"{m // 1440}d"
    if m and m % 60 == 0:
        return f"{m // 60}h"
    return f"{m}m" if m else "0"


def _show(dlg: QDialog, parent: QWidget) -> None:
    dlg.setModal(True)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


def ask_scope(parent: QWidget, verb: str) -> str | None:
    """'this' | 'all' | None (cancelled) for edits/deletes of a repeating event."""
    box = QMessageBox(parent)
    box.setWindowTitle(f"{verb} repeating event")
    box.setText(f"{verb} which events?")
    this_button = box.addButton("Only this event", QMessageBox.ButtonRole.AcceptRole)
    all_button = box.addButton("All events in the series", QMessageBox.ButtonRole.AcceptRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(this_button)
    box.exec()
    if box.clickedButton() is this_button:
        return "this"
    if box.clickedButton() is all_button:
        return "all"
    return None


class EventDialog(QDialog):
    def __init__(self, parent: QWidget, cal, event: Event | None = None, occurrence: Occurrence | None = None,
                 start: datetime | None = None, end: datetime | None = None, all_day: bool = False):
        super().__init__(parent)
        self.cal, self.event, self.occ = cal, event, occurrence
        self.setWindowTitle("Edit event" if event else "New event")
        self.setModal(True)
        self.setSizeGripEnabled(False)
        if event:
            s = occurrence.start if occurrence else event.start
            e = occurrence.end if occurrence else event.end
            all_day = event.all_day
        else:
            s = start or D.now().replace(minute=0, second=0) + timedelta(hours=1)
            e = end or s + (timedelta(days=1) if all_day else timedelta(hours=1))
        self._start0 = s
        shown_end = (e - timedelta(days=1) if e > s else s) if all_day else e
        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)
        self.title_entry = QLineEdit(event.title if event else "")
        self.all_day = QCheckBox("All day")
        self.all_day.setChecked(all_day)
        self.sd, self.st = QLineEdit(_date_text(s)), QLineEdit(D.fmt_time(s))
        self.ed, self.et = QLineEdit(_date_text(shown_end)), QLineEdit(D.fmt_time(shown_end))
        self.loc = QLineEdit(event.location if event else "")
        reminders = event.reminders if event else ([] if all_day else [15])
        self.rem = QLineEdit(", ".join(_compact_minutes(m) for m in reminders))
        self.notes = QTextEdit()
        self.notes.setFixedHeight(82)
        if event:
            self.notes.setPlainText(event.notes)
        form.addRow("Title", self.title_entry)

        self.cat_ids = {NO_CATEGORY: None}
        for c in cal.categories():
            self.cat_ids[c.name] = c.id
        current = cal.category(event.category_id) if event else None
        self.cat = QComboBox()
        self.cat.addItems(list(self.cat_ids))
        self.cat.setCurrentText(current.name if current else NO_CATEGORY)
        cat_row = QWidget()
        cat_layout = QHBoxLayout(cat_row)
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.addWidget(self.cat)
        self.swatch = QLabel("   ")
        self.swatch.setAutoFillBackground(True)
        cat_layout.addWidget(self.swatch)
        form.addRow("Category", cat_row)
        form.addRow("", self.all_day)
        form.addRow("Starts", self._date_time_row(self.sd, self.st))
        form.addRow("Ends", self._date_time_row(self.ed, self.et))
        self.st.setEnabled(not all_day)
        self.et.setEnabled(not all_day)
        self.all_day.toggled.connect(self._on_all_day)
        self.cat.currentTextChanged.connect(self._update_swatch)

        self.rep = QComboBox()
        self.rep.addItems(REPEAT_CHOICES + ([CUSTOM] if event and event.rrule and parse_rrule(event.rrule).custom else []))
        form.addRow("Repeat", self.rep)
        self.rep_note = QLabel()
        form.addRow("", self.rep_note)
        self.interval = QSpinBox()
        self.interval.setRange(1, 99)
        self.interval.setValue(1)
        self.week_days = {code: QCheckBox(label) for code, label in WEEK_ORDER}
        days = QWidget()
        days_layout = QHBoxLayout(days)
        days_layout.setContentsMargins(0, 0, 0, 0)
        for check in self.week_days.values():
            days_layout.addWidget(check)
        self.end_never, self.end_count, self.end_until = QRadioButton("Never"), QRadioButton("After"), QRadioButton("On")
        self.end_never.setChecked(True)
        self.count, self.until = QSpinBox(), QLineEdit()
        self.count.setRange(1, 9999)
        self.count.setValue(10)
        repeat_box = QWidget()
        repeat_layout = QVBoxLayout(repeat_box)
        repeat_layout.setContentsMargins(0, 0, 0, 0)
        every = QHBoxLayout()
        every.addWidget(QLabel("Every"))
        every.addWidget(self.interval)
        self.unit = QLabel("day(s)")
        every.addWidget(self.unit)
        repeat_layout.addLayout(every)
        repeat_layout.addWidget(days)
        ends = QHBoxLayout()
        ends.addWidget(self.end_never)
        ends.addWidget(self.end_count)
        ends.addWidget(self.count)
        ends.addWidget(QLabel("times"))
        ends.addWidget(self.end_until)
        ends.addWidget(self.until)
        repeat_layout.addLayout(ends)
        form.addRow("", repeat_box)
        self.repeat_box, self.days_widget = repeat_box, days
        self.rep.currentTextChanged.connect(self._on_repeat_change)
        self._load_repeat(event.rrule if event else None)
        form.addRow("Reminders", self.rem)
        form.addRow("", QLabel("before the start, e.g. 15, 1h, 1d"))
        form.addRow("Location", self.loc)
        form.addRow("Notes", self.notes)

        buttons = QDialogButtonBox()
        save = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        if event:
            delete = buttons.addButton("Delete", QDialogButtonBox.ButtonRole.DestructiveRole)
            delete.clicked.connect(self._delete)
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        root.addWidget(buttons)
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._save)
        self.title_entry.returnPressed.connect(self._save)
        self._on_repeat_change(self.rep.currentText())
        self._update_swatch()
        _show(self, parent)
        self.title_entry.setFocus()

    @staticmethod
    def _date_time_row(day: QLineEdit, clock: QLineEdit) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(day)
        row.addWidget(clock)
        return w

    def _load_repeat(self, rule: str | None) -> None:
        if not rule:
            return
        p = parse_rrule(rule)
        if p.custom:
            self.rep.setCurrentText(CUSTOM)
            self.rep_note.setText(describe_rrule(rule))
            return
        self.rep.setCurrentText(CHOICE_OF[p.freq])
        self.interval.setValue(p.interval)
        for code in p.byday:
            if code in self.week_days:
                self.week_days[code].setChecked(True)
        if p.count:
            self.end_count.setChecked(True)
            self.count.setValue(p.count)
        elif p.until:
            self.end_until.setChecked(True)
            self.until.setText(f"{p.until.month}/{p.until.day}/{p.until.year}")

    def _on_repeat_change(self, choice: str) -> None:
        enabled = choice not in (NO_REPEAT, CUSTOM)
        self.repeat_box.setVisible(enabled)
        self.unit.setText(UNIT_OF.get(choice, ""))
        self.days_widget.setVisible(choice == "Weekly")
        if choice == "Weekly" and not any(v.isChecked() for v in self.week_days.values()):
            try:
                start = D.parse_date(self.sd.text())
            except ValueError:
                start = self._start0.date()
            self.week_days[WEEKDAY_CODES[start.weekday()]].setChecked(True)

    def _on_all_day(self, checked: bool) -> None:
        self.st.setEnabled(not checked)
        self.et.setEnabled(not checked)

    def _update_swatch(self, *_args) -> None:
        cat = self.cal.category(self.cat_ids.get(self.cat.currentText()))
        self.swatch.setStyleSheet(f"background-color: {cat.color if cat else DEFAULT_COLOR}; border: 1px solid #888")

    def _collect(self) -> dict:
        title = self.title_entry.text().strip()
        if not title:
            raise ValueError("Give the event a title.")
        all_day = self.all_day.isChecked()
        sd, ed = D.parse_date(self.sd.text()), D.parse_date(self.ed.text())
        if all_day:
            start, end = D.day_start(sd), D.day_start(ed) + timedelta(days=1)
            if end <= start:
                raise ValueError("The end date is before the start date.")
        else:
            start = datetime.combine(sd, D.parse_time(self.st.text()))
            end = datetime.combine(ed, D.parse_time(self.et.text()))
            if end < start:
                raise ValueError("The event ends before it starts.")
        return {"title": title, "start": start, "end": end, "all_day": all_day,
                "category_id": self.cat_ids.get(self.cat.currentText()), "location": self.loc.text().strip(),
                "notes": self.notes.toPlainText().strip(), "reminders": D.parse_minute_list(self.rem.text()),
                "rrule": self._collect_rrule(start)}

    def _collect_rrule(self, start: datetime) -> str | None:
        choice = self.rep.currentText()
        if choice == NO_REPEAT:
            return None
        if choice == CUSTOM:
            return self.event.rrule
        interval = self.interval.value()
        byday = [c for c, _ in WEEK_ORDER if self.week_days[c].isChecked()] if choice == "Weekly" else []
        if choice == "Weekly" and not byday:
            byday = [WEEKDAY_CODES[start.weekday()]]
        count = self.count.value() if self.end_count.isChecked() else None
        until = D.parse_date(self.until.text()) if self.end_until.isChecked() else None
        if until and until < start.date():
            raise ValueError("The repeat end date is before the event starts.")
        return build_rrule(FREQ_OF[choice], interval, byday, count, until)

    def _scope(self, verb: str) -> str | None:
        return ask_scope(self, verb)

    def _save(self) -> None:
        try:
            data = self._collect()
        except ValueError as exc:
            QMessageBox.critical(self, "Check the event details", str(exc))
            return
        ev = self.event
        if ev is None:
            fields = {k: v for k, v in data.items() if k != "rrule"}
            new = Event.new(fields.pop("title"), fields.pop("start"), fields.pop("end"), **fields)
            new.rrule = data["rrule"]
            self.cal.save_event(new)
        elif not ev.is_recurring:
            self._apply(ev.copy(), data)
        else:
            scope = self._scope("Edit")
            if scope is None:
                return
            occ_start = self.occ.start if self.occ else ev.start
            if scope == "this":
                fields = {k: v for k, v in data.items() if k != "rrule"}
                self.cal.detach_occurrence(ev.id, occ_start, fields)
            else:
                delta = data["start"] - occ_start
                master = ev.copy()
                master.start = ev.start + delta
                master.exdates = [x + delta for x in ev.exdates]
                data = {**data, "end": master.start + (data["end"] - data["start"]), "start": master.start}
                self._apply(master, data)
        self.accept()

    def _apply(self, ev: Event, data: dict) -> None:
        for key, value in data.items():
            setattr(ev, key, value)
        self.cal.save_event(ev)

    def _delete(self) -> None:
        ev = self.event
        if not ev.is_recurring:
            if QMessageBox.question(self, "Delete event", f"Delete “{ev.title}”?") != QMessageBox.StandardButton.Yes:
                return
            self.cal.delete_event(ev.id)
        else:
            scope = self._scope("Delete")
            if scope == "this":
                self.cal.delete_occurrence(ev.id, self.occ.start if self.occ else ev.start)
            elif scope == "all":
                self.cal.delete_event(ev.id)
            else:
                return
        self.accept()


class CategoryDialog(QDialog):
    """Rename, recolour, add and delete categories; nothing is saved until Save."""

    def __init__(self, parent: QWidget, cal):
        super().__init__(parent)
        self.cal = cal
        self.setWindowTitle("Categories")
        self.rows: list[dict] = []
        self.removed: list[str] = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Categories"))
        root.addWidget(QLabel("Click a colour to change it. Events in a deleted category become uncategorised."))
        self.list_layout = QVBoxLayout()
        root.addLayout(self.list_layout)
        for cat in cal.categories():
            self._add_row(cat)
        add = QPushButton("Add category")
        add.clicked.connect(self._add_new)
        root.addWidget(add, alignment=Qt.AlignmentFlag.AlignLeft)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        _show(self, parent)

    def _add_row(self, cat: Category) -> None:
        frame = QWidget()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        swatch = QPushButton("   ")
        swatch.setStyleSheet(f"background-color: {cat.color}")
        row = {"id": cat.id, "name": QLineEdit(cat.name), "color": cat.color, "frame": frame, "swatch": swatch}
        swatch.clicked.connect(lambda _=False, r=row: self._pick(r))
        layout.addWidget(swatch)
        layout.addWidget(row["name"])
        remove = QPushButton("Delete")
        remove.clicked.connect(lambda _=False, r=row: self._remove(r))
        layout.addWidget(remove)
        self.list_layout.addWidget(frame)
        self.rows.append(row)

    def _add_new(self) -> None:
        color = IMPORT_PALETTE[len(self.rows) % len(IMPORT_PALETTE)]
        self._add_row(Category(new_id("cat"), "New category", color))
        self.rows[-1]["new"] = True

    def _pick(self, row: dict) -> None:
        color = QColorDialog.getColor(QColor(row["color"]), self, "Category colour")
        if color.isValid():
            row["color"] = color.name()
            row["swatch"].setStyleSheet(f"background-color: {row['color']}")

    def _remove(self, row: dict) -> None:
        if not row.get("new"):
            self.removed.append(row["id"])
        row["frame"].deleteLater()
        self.rows.remove(row)

    def _save(self) -> None:
        names = [r["name"].text().strip() for r in self.rows]
        if any(not n for n in names):
            QMessageBox.critical(self, "Check the categories", "Every category needs a name.")
            return
        if len({n.lower() for n in names}) != len(names):
            QMessageBox.critical(self, "Check the categories", "Two categories have the same name.")
            return
        with self.cal.api.vault.batch():
            for cat_id in self.removed:
                self.cal.delete_category(cat_id)
            for row, name in zip(self.rows, names, strict=False):
                self.cal.save_category(Category(row["id"], name, row["color"]))
        self.accept()


class ReadOnlyEventDialog(QDialog):
    """Shows an event from a calendar link without allowing changes."""

    def __init__(self, parent: QWidget, cal, event: Event, occurrence: Occurrence | None = None):
        super().__init__(parent)
        self.setWindowTitle(event.title)
        root = QVBoxLayout(self)
        start = occurrence.start if occurrence else event.start
        end = occurrence.end if occurrence else event.end
        when = (f"{D.fmt_date_long(start.date())} · all day" if event.all_day else
                f"{D.fmt_date_long(start.date())}\n{D.fmt_time(start)} – {D.fmt_time(end)}")
        source = next((s for s in cal.subscriptions() if s.id == event.source), None)
        category = cal.category(event.category_id)
        for text in (event.title, when):
            label = QLabel(text)
            label.setWordWrap(True)
            root.addWidget(label)
        if event.rrule:
            root.addWidget(QLabel(describe_rrule(event.rrule)))
        for label, value in (("Where", event.location), ("Category", category.name if category else ""),
                             ("Reminders", ", ".join(D.fmt_minutes(m) for m in event.reminders) + " before"
                              if event.reminders else "")):
            if value:
                root.addWidget(QLabel(f"{label}: {value}"))
        if event.notes:
            notes = QLabel(f"Notes\n{event.notes}")
            notes.setWordWrap(True)
            root.addWidget(notes)
        name = f"“{source.name}”" if source else "a calendar link"
        detail = QLabel(f"From {name}. It refreshes automatically, so changes are made in the source calendar.")
        detail.setWordWrap(True)
        root.addWidget(detail)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        _show(self, parent)
