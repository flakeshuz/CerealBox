"""Dashboard screen: cards in a two-column grid, with a Customize mode to rearrange them.

Each card reads its data through services exposed by the other modules, so a card for a module
that isn't installed simply shows an empty state.
"""
from __future__ import annotations

import logging
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk

from ...core import dates as D
from ...ui import theme as T
from . import CATALOG, move, set_shown, set_span

log = logging.getLogger("lifeos")
WIDGETS: dict[str, type] = {}


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

    def __init__(self, view: DashboardView):
        self.view = view
        self.api = view.mod.api
        self.body: ttk.Frame | None = None

    def build(self, body: ttk.Frame) -> None:
        self.body = body

    def render(self) -> None:
        """Fill the card. Called on creation and on every refresh."""

    def refresh(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()
        self.render()

    # helpers
    def _call(self, service: str, *args, default=None, **kwargs):
        return self.api.call(service, *args, **kwargs) if self.api.has_service(service) else default

    def _line(self, text: str, style: str = "Card.TLabel") -> None:
        ttk.Label(self.body, text=text, style=style).pack(anchor="w", pady=1)

    def _empty(self, text: str) -> None:
        self._line(text, "CardMuted.TLabel")

    def _button(self, text: str, action: str) -> None:
        ttk.Button(self.body, text=text, style="Small.TButton",
                   command=lambda: self.api.emit("ui.request", action=action)).pack(anchor="w", pady=(8, 0))


@card
class QuickCard(Card):
    key = "quick"
    ACTIONS = (("New event", "new_event"), ("New task", "new_task"), ("New transaction", "new_txn"),
               ("Transfer", "new_transfer"), ("Import bank CSV", "import_csv"))

    def render(self) -> None:
        row = ttk.Frame(self.body, style="CardInner.TFrame")
        row.pack(anchor="w")
        for label, action in self.ACTIONS:
            ttk.Button(row, text=label, command=lambda a=action: self.api.emit("ui.request", action=a)
                       ).pack(side="left", padx=(0, 8), pady=2)


@card
class TodayCard(Card):
    key = "today"

    def render(self) -> None:
        now = D.now()
        day0 = D.day_start(now.date())
        events = self._call("calendar.events_between", day0, day0 + timedelta(days=1), default=[])
        tasks = self._call("tasks.due_today", default=[])
        self._line("Events", "CardSub.TLabel")
        if not events:
            self._empty("Nothing on the calendar today.")
        for r in events[:5]:
            when = "All day" if r["all_day"] else D.fmt_time(r["start"])
            self._line(f"{when}   {r['title']}")
        self._line("Tasks", "CardSub.TLabel")
        if not tasks:
            self._empty("No tasks due today.")
        for t in tasks[:5]:
            late = overdue(t.due, t.has_time, now)
            detail = f"  ·  {D.fmt_time(t.due)}" if t.due and t.has_time else ""
            self._line(f"○ {t.title}{detail}", "CardDanger.TLabel" if late else "Card.TLabel")


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
            self._line(f"{d:%a} {d.day}", "CardSub.TLabel")
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
        self._line(f"{len(tasks)} open" + (f"  ·  {late} overdue" if late else ""), "CardSub.TLabel")
        for t in tasks[:6]:
            style = "CardDanger.TLabel" if overdue(t.due, t.has_time, now) else "Card.TLabel"
            due = ""
            if t.due:
                d = t.due.date()
                day = {0: "today", 1: "tomorrow"}.get((d - now.date()).days) or f"{d:%b} {d.day}"
                due = f"  ·  {day}"
            self._line(f"○ {t.title}{due}", style)
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
            self._line(f"{b.name}   {money(b.amount_cents)}  ·  {when}",
                       "CardDanger.TLabel" if late else "Card.TLabel")
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
        row = ttk.Frame(self.body, style="CardInner.TFrame")
        row.pack(anchor="w", pady=(4, 0))
        for label, value in (("In", s["income"]), ("Out", s["spent"]), ("Net", s["net"])):
            cell = ttk.Frame(row, style="CardInner.TFrame")
            cell.pack(side="left", padx=(0, 22))
            ttk.Label(cell, text=label, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(cell, text=money(value, signed=(label == "Net")), style="CardBig.TLabel").pack(anchor="w")


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
            head = ttk.Frame(self.body, style="CardInner.TFrame")
            head.pack(fill="x", pady=(4, 0))
            ttk.Label(head, text=r["name"], style="Card.TLabel").pack(side="left")
            ttk.Label(head, text=f"{money(r['spent'])} of {money(r['budget'])}",
                      style="CardDanger.TLabel" if over else "CardMuted.TLabel").pack(side="right")
            ttk.Progressbar(self.body, maximum=100, value=pct, length=260,
                            style="Budget.Horizontal.TProgressbar").pack(anchor="w", pady=(2, 0))


@card
class AccountsCard(Card):
    key = "accounts"

    def render(self) -> None:
        accounts = self._call("money.accounts", default=[])
        if not accounts:
            self._empty("No accounts yet. Add one under Money → Manage.")
            return
        for a in accounts[:6]:
            row = ttk.Frame(self.body, style="CardInner.TFrame")
            row.pack(fill="x")
            ttk.Label(row, text=a["name"], style="Card.TLabel").pack(side="left")
            ttk.Label(row, text=money(a["balance"]), style="Card.TLabel").pack(side="right")
        total = sum(a["balance"] for a in accounts)
        self._line(f"Total  {money(total)}", "CardSub.TLabel")


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
                status, style = "problem", "CardDanger.TLabel"
            elif s.last_sync:
                status, style = f"up to date, {s.last_sync:%b %d %H:%M}", "Card.TLabel"
            else:
                status, style = "not checked yet", "CardMuted.TLabel"
            self._line(f"{s.name}  ·  {status}", style)


class DashboardView(ttk.Frame):
    def __init__(self, parent: tk.Misc, mod):
        super().__init__(parent)
        self.mod = mod
        self.api = mod.api
        self.customize = tk.BooleanVar(value=False)
        self._cards: list[Card] = []
        self._timer = None

        top = ttk.Frame(self, padding=(28, 22, 28, 8))
        top.pack(fill="x")
        self.greet = ttk.Label(top, style="Display.TLabel")
        self.greet.pack(side="left")
        self.date_lbl = ttk.Label(top, style="Muted.TLabel")
        self.date_lbl.pack(side="left", padx=12)
        ttk.Checkbutton(top, text="Customize", variable=self.customize, style="Segment.Toolbutton",
                        command=self.rebuild).pack(side="right")
        self.add_btn = ttk.Menubutton(top, text="Add card")
        self.add_menu = tk.Menu(self.add_btn, tearoff=False)
        self.add_btn["menu"] = self.add_menu
        self.reset_btn = ttk.Button(top, text="Reset layout", command=self._reset)

        wrap = ttk.Frame(self)  # scrollable, so every card can be reached on a small window
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=T.BG, highlightthickness=0)
        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")
        self.area = ttk.Frame(self.canvas, padding=(14, 4, 14, 14))
        self._win = self.canvas.create_window((0, 0), window=self.area, anchor="nw")
        self.area.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.area.columnconfigure(0, weight=1, uniform="card")
        self.area.columnconfigure(1, weight=1, uniform="card")

        self._subs = [(p, self._on_data) for p in ("calendar.*", "tasks.*", "money.*", "vault.reloaded")]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self.bind("<Destroy>", self._cleanup, add="+")
        self._tick()
        self.rebuild()

    # ---- lifecycle --------------------------------------------------------------------------
    def _cleanup(self, event) -> None:
        if event.widget is not self:
            return
        for pattern, handler in self._subs:
            self.mod.api.off(pattern, handler)
        if self._timer:
            self.after_cancel(self._timer)

    def _tick(self) -> None:
        self.refresh_cards()
        self._timer = self.after(60_000, self._tick)

    def _on_data(self, **_kw) -> None:
        if self.winfo_exists():
            self.refresh_cards()

    def refresh_cards(self) -> None:
        now = D.now()
        self.greet.config(text=greeting(now))
        self.date_lbl.config(text=f"{now:%A, %B} {now.day}")
        for c in self._cards:
            try:
                c.refresh()
            except Exception:  # one broken card shouldn't take the whole dashboard down
                log.exception("Dashboard card %s failed", c.key)

    # ---- layout -----------------------------------------------------------------------------
    def rebuild(self) -> None:
        for w in self.area.winfo_children():
            w.destroy()
        self._cards = []
        layout = self.mod.layout()
        shown = [i for i in layout if i["shown"]]
        self._fill_add_menu(layout)
        if self.customize.get():
            self.reset_btn.pack(side="right", padx=8)
            self.add_btn.pack(side="right", padx=8)
        else:
            self.reset_btn.pack_forget()
            self.add_btn.pack_forget()
        row = col = 0
        for pos, item in enumerate(shown):
            key, span = item["key"], item["span"]
            if span == 2 and col == 1:
                row, col = row + 1, 0
            cell = ttk.Frame(self.area, style="Card.TFrame", padding=(22, 18))
            cell.grid(row=row, column=col, columnspan=span, sticky="nsew", padx=10, pady=10)
            head = ttk.Frame(cell, style="CardInner.TFrame")
            head.pack(fill="x")
            ttk.Label(head, text=CATALOG[key][0], style="CardTitle.TLabel").pack(side="left")
            if self.customize.get():
                self._controls(head, key, pos, len(shown), span)
            body = ttk.Frame(cell, style="CardInner.TFrame")
            body.pack(fill="both", expand=True, pady=(8, 0))
            widget = WIDGETS[key](self)
            widget.build(body)
            self._cards.append(widget)
            try:
                widget.refresh()
            except Exception:
                log.exception("Dashboard card %s failed", key)
            if span == 2:
                row, col = row + 1, 0
            elif col == 0:
                col = 1
            else:
                row, col = row + 1, 0
        self._bind_wheel(self.area)
        self.refresh_cards()

    def _bind_wheel(self, widget) -> None:
        """Mouse wheel scrolls the dashboard even when the pointer is over a card's text or buttons."""
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, self._wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _wheel(self, e) -> None:
        up = getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0
        self.canvas.yview_scroll(-3 if up else 3, "units")

    def _controls(self, head: ttk.Frame, key: str, pos: int, count: int, span: int) -> None:
        bar = ttk.Frame(head, style="CardInner.TFrame")
        bar.pack(side="right")
        ttk.Button(bar, text="↑", width=2, style="Small.TButton", state="disabled" if pos == 0 else "normal",
                   command=lambda: self._change(lambda lay: move(lay, key, -1))).pack(side="left", padx=1)
        ttk.Button(bar, text="↓", width=2, style="Small.TButton", state="disabled" if pos == count - 1 else "normal",
                   command=lambda: self._change(lambda lay: move(lay, key, 1))).pack(side="left", padx=1)
        ttk.Button(bar, text="Half width" if span == 2 else "Full width", style="Small.TButton",
                   command=lambda: self._change(lambda lay: set_span(lay, key, 1 if span == 2 else 2))
                   ).pack(side="left", padx=4)
        ttk.Button(bar, text="Hide", style="Small.TButton",
                   command=lambda: self._change(lambda lay: set_shown(lay, key, False))).pack(side="left", padx=1)

    def _fill_add_menu(self, layout: list[dict]) -> None:
        self.add_menu.delete(0, "end")
        hidden = [i["key"] for i in layout if not i["shown"]]
        if not hidden:
            self.add_menu.add_command(label="All cards are shown", state="disabled")
        for key in hidden:
            self.add_menu.add_command(label=CATALOG[key][0],
                                      command=lambda k=key: self._change(lambda lay: set_shown(lay, k, True)))

    def _change(self, fn) -> None:
        layout = self.mod.layout()
        self.mod.save_layout(fn(layout))
        self.rebuild()

    def _reset(self) -> None:
        self.mod.reset_layout()
        self.rebuild()
