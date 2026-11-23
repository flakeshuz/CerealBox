"""Dashboard screen implemented with PyQt6 widgets."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from PyQt6.QtCore import QMimeData, QTimer, Qt
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ...core import dates as D
from ...ui import theme as T
from . import CATALOG, move, reorder, set_shown, set_span

log = logging.getLogger("cerealbox")
WIDGETS: dict[str, type] = {}
DASHBOARD_CARD_MIME = "application/x-cerealbox-dashboard-card"


class CardDragHandle(QPushButton):
    def __init__(self, key: str, parent: QWidget):
        super().__init__("↕", parent)
        self.key = key
        self.setToolTip("Drag to reorder this card")
        self.setAccessibleName(f"Drag to reorder {CATALOG[key][0]}")
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._press_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press_pos).manhattanLength()
                >= QApplication.startDragDistance()):
            mime = QMimeData()
            mime.setData(DASHBOARD_CARD_MIME, self.key.encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            self._press_pos = None
            return
        super().mouseMoveEvent(event)


class DashboardCardFrame(QFrame):
    def __init__(self, key: str, on_drop, parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self._on_drop = on_drop
        self.setProperty("card", True)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(DASHBOARD_CARD_MIME):
            self._set_drop_target(True)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(DASHBOARD_CARD_MIME):
            self._set_drop_target(True)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drop_target(False)
        event.accept()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(DASHBOARD_CARD_MIME):
            event.ignore()
            return
        key = bytes(event.mimeData().data(DASHBOARD_CARD_MIME)).decode("utf-8")
        after = event.position().y() >= self.height() / 2
        self._set_drop_target(False)
        self._on_drop(key, self.key, after)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _set_drop_target(self, active: bool) -> None:
        self.setProperty("dropTarget", active)
        self.style().unpolish(self)
        self.style().polish(self)


def card(cls):
    WIDGETS[cls.key] = cls
    return cls


def money(cents: int, signed: bool = False) -> str:
    sign = "-" if cents < 0 else ("+" if signed and cents > 0 else "")
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}${whole:,}.{frac:02d}"


def greeting(now: datetime) -> str:
    h = now.hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 18 else "Good evening")


def overdue(due: datetime | None, has_time: bool, now: datetime) -> bool:
    if not due:
        return False
    return due < now if has_time else due.date() < now.date()


class Card:
    key = ""

    def __init__(self, view: "DashboardView"):
        self.view = view
        self.api = view.mod.api
        self.body: QWidget | None = None

    def build(self, body: QWidget) -> None:
        self.body = body

    def render(self) -> None:
        pass

    def refresh(self) -> None:
        layout = self.body.layout()
        if layout is not None:
            self._clear_layout(layout)
        self.render()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _call(self, service: str, *args, default=None, **kwargs):
        return self.api.call(service, *args, **kwargs) if self.api.has_service(service) else default

    def _line(self, text: str, muted: bool = False, danger: bool = False) -> None:
        label = QLabel(text)
        if muted:
            label.setStyleSheet(f"color: {T.MUTED};")
        if danger:
            label.setStyleSheet(f"color: {T.NOW};")
        label.setWordWrap(True)
        self.body.layout().addWidget(label)

    def _empty(self, text: str) -> None:
        self._line(text, muted=True)

    def _button(self, text: str, action: str) -> None:
        button = QPushButton(text)
        button.clicked.connect(lambda: self.api.emit("ui.request", action=action))
        self.body.layout().addWidget(button)


@card
class QuickCard(Card):
    key = "quick"
    ACTIONS = (("New event", "new_event"), ("New task", "new_task"), ("New transaction", "new_txn"),
               ("Transfer", "new_transfer"), ("Import bank CSV", "import_csv"))

    def render(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.body.layout().addLayout(grid)
        for index, (label, action) in enumerate(self.ACTIONS):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=action: self.api.emit("ui.request", action=a))
            grid.addWidget(button, index // 2, index % 2)


@card
class TodayCard(Card):
    key = "today"

    def render(self) -> None:
        now = D.now()
        day0 = D.day_start(now.date())
        events = self._call("calendar.events_between", day0, day0 + timedelta(days=1), default=[])
        tasks = self._call("tasks.due_today", default=[])
        open_tasks = self._call("tasks.open_tasks", default=[])
        overdue_tasks = [task for task in open_tasks if overdue(task.due, task.has_time, now)]
        self._line("Overdue", danger=True)
        if not overdue_tasks:
            self._empty("Nothing overdue.")
        for task in overdue_tasks[:5]:
            due = f"  ·  {task.due:%b} {task.due.day}" if task.due else ""
            self._line(f"! {task.title}{due}", danger=True)
        self._line("Today")
        if not events:
            self._empty("Nothing on the calendar today.")
        else:
            for r in events[:5]:
                when = "All day" if r["all_day"] else D.fmt_time(r["start"])
                self._line(f"{when}   {r['title']}")
        self._line("Tasks")
        if not tasks:
            self._empty("No tasks due today.")
        else:
            for task in tasks[:5]:
                if task in overdue_tasks:
                    continue
                detail = f"  ·  {D.fmt_time(task.due)}" if task.due and task.has_time else ""
                self._line(f"○ {task.title}{detail}")
        if len(overdue_tasks) > 5:
            self._empty(f"+{len(overdue_tasks) - 5} more overdue")
        if len(tasks) > 5:
            self._empty(f"+{len(tasks) - 5} more due today")


@card
class WeekCard(Card):
    key = "week"

    def render(self) -> None:
        day0 = D.day_start(date.today())
        rows = self._call("calendar.events_between", day0, day0 + timedelta(days=7), default=[])
        if not rows:
            self._empty("Nothing in the next 7 days.")
            return
        by_day: dict[date, list] = {}
        for r in rows:
            by_day.setdefault(r["start"].date(), []).append(r)
        shown = 0
        for d in sorted(by_day):
            if shown >= 9:
                break
            self._line(f"{d:%a} {d.day}")
            for r in by_day[d][:3]:
                shown += 1
                when = "All day" if r["all_day"] else D.fmt_time(r["start"])
                self._line(f"    {when}   {r['title']}")
            if len(by_day[d]) > 3:
                self._empty(f"    +{len(by_day[d]) - 3} more")


@card
class TasksCard(Card):
    key = "tasks"

    def render(self) -> None:
        now = D.now()
        tasks = self._call("tasks.open_tasks", default=[])
        if not tasks:
            self._empty("All clear. No open tasks.")
            return
        late = sum(1 for t in tasks if overdue(t.due, t.has_time, now))
        self._line(f"{len(tasks)} open" + (f"  ·  {late} overdue" if late else ""))
        for t in tasks[:6]:
            is_late = overdue(t.due, t.has_time, now)
            due = ""
            if t.due:
                d = t.due.date()
                day = {0: "today", 1: "tomorrow"}.get((d - now.date()).days) or f"{d:%b} {d.day}"
                due = f"  ·  {day}"
            self._line(f"○ {t.title}{due}", danger=is_late)
        self._button("Open tasks", "open_tasks")


@card
class BillsCard(Card):
    key = "bills"

    def render(self) -> None:
        today = date.today()
        bills = self._call("money.bills_due", 14, default=[])
        if not bills:
            self._empty("No bills due in the next two weeks.")
            return
        for b in bills[:6]:
            late = b.due < today
            when = "overdue" if late else ("today" if b.due == today else f"{b.due:%b} {b.due.day}")
            self._line(f"{b.name}   {money(b.amount_cents)}  ·  {when}", danger=late)
        self._button("Open bills", "open_bills")


@card
class CashflowCard(Card):
    key = "cashflow"

    def render(self) -> None:
        now = D.now()
        s = self._call("money.month_summary", now.year, now.month)
        if not s:
            self._empty("Add an account to see this month's money.")
            return
        row = QHBoxLayout()
        self.body.layout().addLayout(row)
        for label, value in (("In", s["income"]), ("Out", s["spent"]), ("Net", s["net"])):
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.addWidget(QLabel(label))
            item_layout.addWidget(QLabel(money(value, signed=(label == "Net"))))
            row.addWidget(item)
        row.addStretch()


@card
class BudgetCard(Card):
    key = "budget"

    def render(self) -> None:
        now = D.now()
        s = self._call("money.month_summary", now.year, now.month)
        rows = [r for r in (s["categories"] if s else []) if r["budget"]]
        if not rows:
            self._empty("No budgets yet. Set them under Money → Manage.")
            return
        for r in rows[:6]:
            pct = min(100, round(r["spent"] / r["budget"] * 100)) if r["budget"] else 0
            over = r["spent"] > r["budget"]
            head = QHBoxLayout()
            name = QLabel(r["name"])
            value = QLabel(f"{money(r['spent'])} of {money(r['budget'])}")
            if over:
                value.setStyleSheet(f"color: {T.NOW}")
            head.addWidget(name)
            head.addStretch()
            head.addWidget(value)
            self.body.layout().addLayout(head)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(pct)
            self.body.layout().addWidget(bar)


@card
class AccountsCard(Card):
    key = "accounts"

    def render(self) -> None:
        accounts = self._call("money.accounts", default=[])
        if not accounts:
            self._empty("No accounts yet. Add one under Money → Manage.")
            return
        for a in accounts[:6]:
            row = QHBoxLayout()
            row.addWidget(QLabel(a["name"]))
            row.addStretch()
            row.addWidget(QLabel(money(a["balance"])))
            self.body.layout().addLayout(row)
        total = sum(a["balance"] for a in accounts)
        self._line(f"Total  {money(total)}")


@card
class LinksCard(Card):
    key = "links"

    def render(self) -> None:
        subs = self._call("calendar.subscriptions", default=[])
        if not subs:
            self._empty("No calendar links. Add one under Calendar → More.")
            return
        for s in subs[:6]:
            if s.last_error:
                status = "problem"
                danger = True
            elif s.last_sync:
                status = f"up to date, {s.last_sync:%b %d %H:%M}"
                danger = False
            else:
                status = "not checked yet"
                danger = False
            self._line(f"{s.name}  ·  {status}", muted=not danger and not s.last_sync, danger=danger)


class DashboardView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        self.api = mod.api
        self.customize = False
        self._cards: list[Card] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 18, 28, 8)
        top = QHBoxLayout()
        self.greet = QLabel()
        self.greet.setStyleSheet("font-size: 20px; font-weight: bold")
        self.date_lbl = QLabel()
        top.addWidget(self.greet)
        top.addWidget(self.date_lbl)
        top.addStretch()
        self.customize_box = QCheckBox("Customize")
        self.customize_box.setAccessibleName("Customize dashboard")
        self.customize_box.toggled.connect(self._toggle_customize)
        top.addWidget(self.customize_box)
        self.add_menu_btn = QPushButton("Add card")
        self.add_menu_btn.setMenu(QMenu(self.add_menu_btn))
        top.addWidget(self.add_menu_btn)
        self.reset_btn = QPushButton("Reset layout")
        self.reset_btn.setAccessibleName("Reset dashboard layout")
        self.reset_btn.clicked.connect(self._reset)
        top.addWidget(self.reset_btn)
        self.customize_hint = QLabel("Drag cards to reorder, or use the arrow buttons.")
        self.customize_hint.setObjectName("muted")
        self.customize_hint.setWordWrap(True)
        root.addLayout(top)
        root.addWidget(self.customize_hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.area = QWidget()
        self.area.setObjectName("dashboardArea")
        self.grid = QGridLayout(self.area)
        self.grid.setContentsMargins(14, 4, 14, 14)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.area)
        root.addWidget(self.scroll)

        self._subs = [(p, self._on_data) for p in ("calendar.*", "tasks.*", "money.*", "vault.reloaded")]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self.timer = QTimer(self)
        self.timer.setInterval(60_000)
        self.timer.timeout.connect(self.refresh_cards)
        self.timer.start()
        self.rebuild()
        self.refresh_cards()

    def closeEvent(self, event) -> None:
        for pattern, handler in self._subs:
            self.mod.api.off(pattern, handler)
        super().closeEvent(event)

    def _toggle_customize(self, checked: bool) -> None:
        self.customize = checked
        self.rebuild()

    def _on_data(self, **_kw) -> None:
        self.refresh_cards()

    def refresh_cards(self) -> None:
        now = D.now()
        self.greet.setText(greeting(now))
        self.date_lbl.setText(f"{now:%A, %B} {now.day}")
        for c in self._cards:
            try:
                c.refresh()
            except Exception:
                log.exception("Dashboard card %s failed", c.key)

    def theme_changed(self) -> None:
        self.refresh_cards()

    def rebuild(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = []
        layout = self.mod.layout()
        shown = [i for i in layout if i["shown"]]
        self._fill_add_menu(layout)
        self.add_menu_btn.setVisible(self.customize)
        self.reset_btn.setVisible(self.customize)
        self.customize_hint.setVisible(self.customize)
        row = col = 0
        for pos, item in enumerate(shown):
            key, span = item["key"], item["span"]
            if span == 2 and col == 1:
                row, col = row + 1, 0
            card_widget = DashboardCardFrame(key, self._reorder_cards, self.area)
            card_widget.setObjectName("dashboardCard")
            card_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            card_layout = QVBoxLayout(card_widget)
            card_layout.setContentsMargins(22, 18, 22, 18)
            head = QHBoxLayout()
            title = QLabel(CATALOG[key][0])
            title.setStyleSheet("font-weight: bold")
            head.addWidget(title)
            head.addStretch()
            if self.customize:
                head.addWidget(CardDragHandle(key, card_widget))
                self._controls(head, key, pos, len(shown), span)
            card_layout.addLayout(head)
            body = QWidget()
            body.setLayout(QVBoxLayout())
            body.layout().setContentsMargins(0, 8, 0, 0)
            card_layout.addWidget(body)
            widget = WIDGETS[key](self)
            widget.build(body)
            self._cards.append(widget)
            try:
                widget.refresh()
            except Exception:
                log.exception("Dashboard card %s failed", key)
            self.grid.addWidget(card_widget, row, col, 1, span, Qt.AlignmentFlag.AlignTop)
            if span == 2:
                row, col = row + 1, 0
            elif col == 0:
                col = 1
            else:
                row, col = row + 1, 0
        self.refresh_cards()

    def _controls(self, head: QHBoxLayout, key: str, pos: int, count: int, span: int) -> None:
        up = QPushButton("↑")
        up.setAccessibleName(f"Move {CATALOG[key][0]} earlier")
        up.setToolTip(f"Move {CATALOG[key][0]} earlier")
        up.setEnabled(pos != 0)
        up.clicked.connect(lambda: self._change(lambda lay: move(lay, key, -1)))
        head.addWidget(up)
        down = QPushButton("↓")
        down.setAccessibleName(f"Move {CATALOG[key][0]} later")
        down.setToolTip(f"Move {CATALOG[key][0]} later")
        down.setEnabled(pos != count - 1)
        down.clicked.connect(lambda: self._change(lambda lay: move(lay, key, 1)))
        head.addWidget(down)
        width = QPushButton("Half width" if span == 2 else "Full width")
        width.setAccessibleName(f"Change width of {CATALOG[key][0]}")
        width.clicked.connect(lambda: self._change(lambda lay: set_span(lay, key, 1 if span == 2 else 2)))
        head.addWidget(width)
        hide = QPushButton("Hide")
        hide.setAccessibleName(f"Hide {CATALOG[key][0]}")
        hide.clicked.connect(lambda: self._change(lambda lay: set_shown(lay, key, False)))
        head.addWidget(hide)

    def _fill_add_menu(self, layout: list[dict]) -> None:
        menu = self.add_menu_btn.menu()
        menu.clear()
        hidden = [i["key"] for i in layout if not i["shown"]]
        if not hidden:
            action = menu.addAction("All cards are shown")
            action.setEnabled(False)
        for key in hidden:
            action = menu.addAction(CATALOG[key][0])
            action.triggered.connect(lambda _checked=False, k=key: self._change(lambda lay: set_shown(lay, k, True)))

    def _change(self, fn) -> None:
        layout = self.mod.layout()
        self.mod.save_layout(fn(layout))
        self.rebuild()

    def _reorder_cards(self, key: str, target_key: str, after: bool) -> None:
        self._change(lambda layout: reorder(layout, key, target_key, after=after))

    def _reset(self) -> None:
        self.mod.reset_layout()
        self.rebuild()
