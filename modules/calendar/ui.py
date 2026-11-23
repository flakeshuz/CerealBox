"""The calendar screen: month, week and day views drawn on Tk canvases.

Interaction: click an event to edit it. Double-click an empty day or time slot to add one.
Keys: Left/Right = previous/next, T = today.
"""
from __future__ import annotations

import logging
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ...core import dates as D
from ...ui import theme as T
from .dialogs import CategoryDialog, EventDialog, ReadOnlyEventDialog, ask_scope
from .models import Occurrence
from .subscriptions import Subscription, normalize_url

HOUR_H = 52  # pixels per hour in the week/day views
GUTTER = 58  # width of the hour-label column
CHIP_H = 18  # height of one event chip


def _modal(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.transient(parent.winfo_toplevel())
    T.center(win, parent)
    win.wait_visibility()
    win.grab_set()


class CalendarView(ttk.Frame):
    def __init__(self, parent: tk.Misc, cal):
        super().__init__(parent)
        self.cal = cal
        self.mode = "month"
        self.cursor = date.today()
        self.first_weekday = D.SUNDAY
        self.hidden: set = set()  # category ids (or None) hidden by the filter
        self._hits: list = []
        self._head_hits: list = []
        self._pending = False
        self._press_info: dict | None = None  # what the mouse went down on
        self._dragging = False
        self._pending_edit = None  # a click waits briefly so a double-click doesn't open two editors
        self._col_days: list | None = None  # dates shown in week/day columns, left to right
        self._colw = 1.0
        self._scroll_frac = 6.5 / 24  # week/day views open scrolled to just before 7 AM
        self._drawn_timed = False
        self.f_small, self.f_bold = T.font(9), T.font(9, True)
        self.f_day, self.f_hour, self.f_num = T.font(10, True), T.font(8), T.font(15, True)

        self._build_toolbar()
        self._build_canvases()
        self._rebuild_filter_menu()
        self._subs = [("calendar.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            cal.api.on(pattern, handler)
        self._timer = self._idle = None
        self._tick_timer()
        self.bind("<Destroy>", self._cleanup, add="+")

    # ---- construction ----------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, padding=(14, 12, 14, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="‹", width=3, command=lambda: self.step(-1)).pack(side="left")
        ttk.Button(bar, text="Today", command=self.go_today).pack(side="left", padx=6)
        ttk.Button(bar, text="›", width=3, command=lambda: self.step(1)).pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.title_var, style="Title.TLabel").pack(side="left", padx=18)

        right = ttk.Frame(bar)
        right.pack(side="right")
        self.mode_var = tk.StringVar(value=self.mode)
        for label in ("Month", "Week", "Day"):
            ttk.Radiobutton(right, text=label, value=label.lower(), variable=self.mode_var,
                            style="Segment.Toolbutton", command=lambda: self.set_mode(self.mode_var.get())
                            ).pack(side="left")
        ttk.Button(right, text="New event", style="Accent.TButton", command=self.new_event).pack(side="left", padx=(14, 6))
        more = ttk.Menubutton(right, text="More")
        more.pack(side="left")
        menu = tk.Menu(more, tearoff=False)
        more["menu"] = menu
        menu.add_command(label="Import .ics file…", command=self.import_ics)
        menu.add_command(label="Export .ics file…", command=self.export_ics)
        menu.add_command(label="Calendar links (.ics)…", command=self.open_subscriptions)
        menu.add_separator()
        self.filter_menu = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="Show categories", menu=self.filter_menu)
        menu.add_command(label="Manage categories…", command=self.manage_categories)

    def _build_canvases(self) -> None:
        border = tk.Frame(self, bg=T.LINE, padx=1, pady=1)
        border.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        border.rowconfigure(1, weight=1)
        border.columnconfigure(0, weight=1)
        self.head = tk.Canvas(border, height=1, bg=T.SURFACE, highlightthickness=0)
        self.body = tk.Canvas(border, bg=T.SURFACE, highlightthickness=0, yscrollincrement=13)
        self.vbar = ttk.Scrollbar(border, orient="vertical", command=self.body.yview)
        self.body.configure(yscrollcommand=self.vbar.set)
        self.head_fill = tk.Frame(border, bg=T.SURFACE)  # fills the corner above the scrollbar
        self.head.grid(row=0, column=0, sticky="ew")
        self.head_fill.grid(row=0, column=1, sticky="nsew")
        self.body.grid(row=1, column=0, sticky="nsew")
        self.vbar.grid(row=1, column=1, sticky="ns")
        self.head.grid_remove()
        self.head_fill.grid_remove()
        self.vbar.grid_remove()

        self.body.bind("<Configure>", lambda _e: self.schedule_redraw())
        for canvas, which in ((self.body, "body"), (self.head, "head")):
            canvas.bind("<Button-1>", lambda e, w=which: self._press(w, e))
            canvas.bind("<B1-Motion>", lambda e, w=which: self._motion(w, e))
            canvas.bind("<ButtonRelease-1>", lambda e, w=which: self._release(w, e))
            canvas.bind("<Double-Button-1>", lambda e, w=which: self._double(w, e))
            canvas.bind("<MouseWheel>", self._wheel)
            canvas.bind("<Button-4>", self._wheel)
            canvas.bind("<Button-5>", self._wheel)
            canvas.bind("<Left>", lambda _e: self.step(-1))
            canvas.bind("<Right>", lambda _e: self.step(1))
            canvas.bind("<Key-t>", lambda _e: self.go_today())

    def _rebuild_filter_menu(self) -> None:
        self.filter_menu.delete(0, "end")
        self._filter_vars: dict = {}
        entries = [(c.id, c.name) for c in self.cal.categories()] + [(None, "No category")]
        for key, label in entries:
            var = tk.BooleanVar(value=key not in self.hidden)
            self._filter_vars[key] = var
            self.filter_menu.add_checkbutton(label=label, variable=var, command=lambda k=key: self._toggle(k))

    def _toggle(self, key) -> None:
        (self.hidden.discard if self._filter_vars[key].get() else self.hidden.add)(key)
        self.redraw()

    # ---- navigation ------------------------------------------------------------------
    def step(self, n: int) -> None:
        if self.mode == "month":
            self.cursor = D.add_months(self.cursor.replace(day=1), n)
        else:
            self.cursor += timedelta(days=(7 if self.mode == "week" else 1) * n)
        self.redraw()

    def go_today(self) -> None:
        self.cursor = date.today()
        self.redraw()

    def set_mode(self, mode: str) -> None:
        today = date.today()
        if mode != "month" and self.mode == "month" and (self.cursor.year, self.cursor.month) == (today.year, today.month):
            self.cursor = today  # month -> week/day lands on today when it's in view
        self.mode = mode
        self.mode_var.set(mode)
        if mode == "month":
            self.head.grid_remove()
            self.head_fill.grid_remove()
            self.vbar.grid_remove()
        else:
            self.head.grid()
            self.head_fill.grid()
            self.vbar.grid()
        self.update_idletasks()
        self.redraw()

    def _range(self) -> tuple[date, date]:
        """Visible dates as [first, last_exclusive)."""
        if self.mode == "month":
            grid = D.month_grid(self.cursor.year, self.cursor.month, self.first_weekday)
            return grid[0][0], grid[-1][-1] + timedelta(days=1)
        if self.mode == "week":
            ws = D.week_start(self.cursor, self.first_weekday)
            return ws, ws + timedelta(days=7)
        return self.cursor, self.cursor + timedelta(days=1)

    def _title(self) -> str:
        if self.mode == "month":
            return f"{self.cursor:%B %Y}"
        first, last = self._range()
        end = last - timedelta(days=1)
        if self.mode == "day":
            return D.fmt_date_long(first)
        if first.month == end.month:
            return f"{first:%b} {first.day} – {end.day}, {end.year}"
        return f"{first:%b} {first.day} – {end:%b} {end.day}, {end.year}"

    # ---- redraw plumbing -------------------------------------------------------------
    def _on_change(self, topic: str = "", **_) -> None:
        if topic == "calendar.categories.changed" or topic == "vault.reloaded":
            self._rebuild_filter_menu()
        self.schedule_redraw()

    def _cleanup(self, event) -> None:
        if event.widget is not self:
            return
        for pattern, handler in self._subs:
            self.cal.api.off(pattern, handler)
        for job in (self._timer, self._idle):
            if job:
                self.after_cancel(job)

    def schedule_redraw(self) -> None:
        if not self._pending:
            self._pending = True
            self._idle = self.after_idle(self.redraw)

    def _tick(self) -> None:
        self.schedule_redraw()  # keeps the "now" line and today highlight fresh
        self._tick_timer()

    def _tick_timer(self) -> None:
        self._timer = self.after(60_000, self._tick)

    def redraw(self) -> None:
        self._pending = False
        if self.mode != "month" and self._drawn_timed:
            self._scroll_frac = self.body.yview()[0]
        self.body.delete("all")
        self.head.delete("all")
        self._hits, self._head_hits = [], []
        self.title_var.set(self._title())
        w, h = self.body.winfo_width(), self.body.winfo_height()
        if w < 80 or h < 80:
            return
        first, last = self._range()
        occs = self.cal.occurrences_between(D.day_start(first), D.day_start(last), self.hidden)
        if self.mode == "month":
            self._draw_month(occs, w, h)
            self._drawn_timed = False
        else:
            self._draw_timed(occs, w)
            self._drawn_timed = True

    # ---- drawing helpers -------------------------------------------------------------
    @staticmethod
    def _fit(text: str, font, max_width: float) -> str:
        text = text.replace("\n", " ")
        if font.measure(text) <= max_width:
            return text
        while text and font.measure(text + "…") > max_width:
            text = text[:-1]
        return text.rstrip() + "…" if text else ""

    @staticmethod
    def _bucket(occs: list[Occurrence]) -> dict[date, list[Occurrence]]:
        by_day: dict[date, list[Occurrence]] = defaultdict(list)
        for o in occs:
            for d in o.days():
                by_day[d].append(o)
        for items in by_day.values():
            items.sort(key=lambda o: (not o.all_day, o.start, o.title.lower()))
        return by_day

    @staticmethod
    def _layout(items: list[tuple]) -> list[tuple]:
        """Side-by-side columns for overlapping events: -> (start, end, occ, column, n_columns)."""
        result: list[tuple] = []
        cluster: list[tuple] = []
        col_ends: list[datetime] = []
        cluster_end = None

        def flush() -> None:
            n = len(col_ends)
            result.extend((s, e, o, col, n) for s, e, o, col in cluster)

        for s, e, o in sorted(items, key=lambda t: (t[0], t[1])):
            if cluster and s >= cluster_end:
                flush()
                cluster, col_ends, cluster_end = [], [], None
            for col, end in enumerate(col_ends):
                if s >= end:
                    col_ends[col] = e
                    break
            else:
                col = len(col_ends)
                col_ends.append(e)
            cluster.append((s, e, o, col))
            cluster_end = e if cluster_end is None else max(cluster_end, e)
        if cluster:
            flush()
        return result

    # ---- month view ------------------------------------------------------------------
    def _draw_month(self, occs: list[Occurrence], w: int, h: int) -> None:
        c = self.body
        c.configure(scrollregion=(0, 0, w, h))
        grid = D.month_grid(self.cursor.year, self.cursor.month, self.first_weekday)
        hdr, cw = 32, w / 7
        ch = (h - hdr) / 6
        today = date.today()
        by_day = self._bucket(occs)
        cap = max(0, int((ch - 34) // (CHIP_H + 2)))
        for i, d in enumerate(grid[0]):
            c.create_text(i * cw + 10, hdr / 2, text=f"{d:%a}", anchor="w", fill=T.MUTED, font=self.f_small)
        for r, week in enumerate(grid):
            for i, d in enumerate(week):
                x0, y0 = i * cw, hdr + r * ch
                x1, y1 = x0 + cw, y0 + ch
                in_month = d.month == self.cursor.month
                fill = T.TODAY_BG if d == today else (T.SURFACE if in_month else T.DIM)
                c.create_rectangle(x0, y0, x1, y1, fill=fill, outline=T.LINE)
                self._hits.append((x0, y0, x1, y1, "day", d))
                if d == today:
                    c.create_oval(x0 + 6, y0 + 5, x0 + 28, y0 + 27, fill=T.ACCENT, outline="")
                    c.create_text(x0 + 17, y0 + 16, text=str(d.day), fill="#FFFFFF", font=self.f_day)
                else:
                    label = f"{d:%b} {d.day}" if d.day == 1 else str(d.day)
                    c.create_text(x0 + 10, y0 + 16, text=label, anchor="w", font=self.f_day,
                                  fill=T.INK if in_month else T.FAINT)
                items = by_day.get(d, [])
                shown = items if len(items) <= cap else items[: max(cap - 1, 0)]
                y = y0 + 32
                for o in shown:
                    self._month_chip(c, o, x0 + 4, y, x1 - 4)
                    y += CHIP_H + 2
                if len(items) > len(shown) and y + CHIP_H <= y1 + 2:
                    c.create_text(x0 + 10, y + CHIP_H / 2, anchor="w", fill=T.MUTED, font=self.f_small,
                                  text=f"+{len(items) - len(shown)} more")
                    self._hits.append((x0 + 4, y, x1 - 4, y + CHIP_H, "more", d))

    def _month_chip(self, c: tk.Canvas, o: Occurrence, x0: float, y: float, x1: float) -> None:
        col = self.cal.color_of(o.event)
        mid = y + CHIP_H / 2
        if o.all_day or len(o.days()) > 1:
            c.create_rectangle(x0, y, x1, y + CHIP_H, fill=col, outline="")
            c.create_text(x0 + 6, mid, anchor="w", text=self._fit(o.title, self.f_small, x1 - x0 - 12),
                          fill=T.on_color(col), font=self.f_small)
        else:
            c.create_oval(x0 + 4, mid - 3, x0 + 10, mid + 3, fill=col, outline="")
            c.create_text(x0 + 15, mid, anchor="w", fill=T.INK, font=self.f_small,
                          text=self._fit(f"{D.fmt_time_short(o.start)} {o.title}", self.f_small, x1 - x0 - 18))
        self._hits.append((x0, y, x1, y + CHIP_H, "event", o))

    # ---- week / day view -------------------------------------------------------------
    def _draw_timed(self, occs: list[Occurrence], w: int) -> None:
        first, last = self._range()
        n = (last - first).days
        days = [first + timedelta(days=i) for i in range(n)]
        colw = (w - GUTTER) / n
        self._colw, self._col_days = colw, days
        today = date.today()

        # all-day strip: pack multi-day bars into rows
        rows: list[list[tuple[int, int]]] = []
        placed: list[tuple[Occurrence, int, int, int]] = []
        allday = sorted((o for o in occs if o.all_day), key=lambda o: (o.start, -(o.end - o.start).total_seconds()))
        for o in allday:
            c0 = max((o.days()[0] - first).days, 0)
            c1 = min((o.days()[-1] - first).days, n - 1)
            for r, used in enumerate(rows):
                if all(c1 < a or c0 > b for a, b in used):
                    used.append((c0, c1))
                    placed.append((o, c0, c1, r))
                    break
            else:
                rows.append([(c0, c1)])
                placed.append((o, c0, c1, len(rows) - 1))
        shown_rows = min(len(rows), 4)
        hdr = 50
        head_h = hdr + shown_rows * (CHIP_H + 3) + (6 if shown_rows else 0)
        hd = self.head
        hd.configure(height=head_h)
        for i, d in enumerate(days):
            x0 = GUTTER + i * colw
            if d == today:
                hd.create_rectangle(x0, 0, x0 + colw, head_h, fill=T.TODAY_BG, outline="")
        for i, d in enumerate(days):
            x0 = GUTTER + i * colw
            hd.create_line(x0, 0, x0, head_h, fill=T.LINE)
            hd.create_text(x0 + 10, 15, anchor="w", text=f"{d:%a}", font=self.f_small,
                           fill=T.ACCENT if d == today else T.MUTED)
            hd.create_text(x0 + 10, 35, anchor="w", text=str(d.day), font=self.f_num,
                           fill=T.ACCENT if d == today else T.INK)
            self._head_hits.append((x0, 0, x0 + colw, head_h, "allday", d))
        hd.create_line(0, head_h - 1, w, head_h - 1, fill=T.LINE)
        if shown_rows:
            hd.create_text(GUTTER - 8, hdr + CHIP_H / 2, anchor="e", text="all day", fill=T.MUTED, font=self.f_hour)
        for o, c0, c1, r in placed:
            if r >= shown_rows:
                continue
            x0, x1 = GUTTER + c0 * colw + 3, GUTTER + (c1 + 1) * colw - 3
            y = hdr + r * (CHIP_H + 3)
            col = self.cal.color_of(o.event)
            hd.create_rectangle(x0, y, x1, y + CHIP_H, fill=col, outline="")
            hd.create_text(x0 + 6, y + CHIP_H / 2, anchor="w", font=self.f_small, fill=T.on_color(col),
                           text=self._fit(o.title, self.f_small, x1 - x0 - 12))
            self._head_hits.append((x0, y, x1, y + CHIP_H, "event", o))
        extra = sum(1 for p in placed if p[3] >= shown_rows)
        if extra:
            hd.create_text(GUTTER - 8, head_h - 10, anchor="e", text=f"+{extra}", fill=T.MUTED, font=self.f_small)

        # scrolling hour grid
        c, total = self.body, 24 * HOUR_H
        c.configure(scrollregion=(0, 0, w, total))
        for i, d in enumerate(days):
            if d == today:
                c.create_rectangle(GUTTER + i * colw, 0, GUTTER + (i + 1) * colw, total, fill=T.TODAY_BG, outline="")
        for hr in range(24):
            y = hr * HOUR_H
            c.create_line(GUTTER, y, w, y, fill=T.LINE)
            c.create_line(GUTTER, y + HOUR_H / 2, w, y + HOUR_H / 2, fill=T.LINE_SOFT)
            if hr:
                c.create_text(GUTTER - 8, y, anchor="e", text=D.fmt_hour(hr), fill=T.MUTED, font=self.f_hour)
        for i in range(n + 1):
            c.create_line(GUTTER + i * colw, 0, GUTTER + i * colw, total, fill=T.LINE)

        for i, d in enumerate(days):
            x0 = GUTTER + i * colw
            self._hits.append((x0, 0, x0 + colw, total, "slot", d))
            day0 = D.day_start(d)
            day1 = day0 + timedelta(days=1)
            items = []
            for o in occs:
                if o.all_day:
                    continue
                end_eff = max(o.end, o.start + timedelta(minutes=30))
                if o.start < day1 and end_eff > day0:
                    items.append((max(o.start, day0), min(end_eff, day1), o))
            for s, e, o, col, ncols in self._layout(items):
                width = (colw - 6) / ncols
                bx0 = x0 + 3 + col * width
                bx1 = bx0 + width - 2
                y0 = (s - day0).total_seconds() / 3600 * HOUR_H + 1
                y1 = (e - day0).total_seconds() / 3600 * HOUR_H - 1
                color = self.cal.color_of(o.event)
                c.create_rectangle(bx0, y0, bx1, y1, fill=T.tint(color, 0.8), outline=T.tint(color, 0.5))
                c.create_rectangle(bx0, y0, bx0 + 4, y1, fill=color, outline="")
                tw = bx1 - bx0 - 12
                c.create_text(bx0 + 9, y0 + 3, anchor="nw", font=self.f_bold, fill=T.shade(color, 0.55),
                              text=self._fit(o.title, self.f_bold, tw))
                if y1 - y0 >= 38:
                    sub = f"{D.fmt_time(o.start)} – {D.fmt_time(o.end)}"
                    if o.event.location:
                        sub += f"  ·  {o.event.location}"
                    c.create_text(bx0 + 9, y0 + 18, anchor="nw", font=self.f_small, fill=T.shade(color, 0.4),
                                  text=self._fit(sub, self.f_small, tw))
                self._hits.append((bx0, y0, bx1, y1, "event", o))

        if today in days:
            x0 = GUTTER + days.index(today) * colw
            y = (datetime.now() - D.day_start(today)).total_seconds() / 3600 * HOUR_H
            c.create_line(x0, y, x0 + colw, y, fill=T.NOW, width=2)
            c.create_oval(x0 - 4, y - 4, x0 + 4, y + 4, fill=T.NOW, outline="")
        c.yview_moveto(self._scroll_frac)

    # ---- mouse / keyboard ------------------------------------------------------------
    def _find(self, which: str, e: tk.Event):
        canvas = self.body if which == "body" else self.head
        hits = self._hits if which == "body" else self._head_hits
        x, y = canvas.canvasx(e.x), canvas.canvasy(e.y)
        for x0, y0, x1, y1, kind, payload in reversed(hits):  # last drawn = on top
            if x0 <= x <= x1 and y0 <= y <= y1:
                return kind, payload, y
        return None, None, y

    # ---- mouse: click to edit, drag to move ---------------------------------------------------
    @staticmethod
    def _snap(minutes: float) -> int:
        return round(minutes / 15) * 15

    def _column_at(self, cx: float) -> int | None:
        if not self._col_days or cx < GUTTER:
            return None
        i = int((cx - GUTTER) // self._colw)
        return i if 0 <= i < len(self._col_days) else None

    def _day_at(self, cx: float, cy: float):
        for x0, y0, x1, y1, kind, payload in self._hits:
            if kind == "day" and x0 <= cx <= x1 and y0 <= cy <= y1:
                return payload
        return None

    def _cancel_pending_edit(self) -> None:
        if self._pending_edit:
            self.after_cancel(self._pending_edit)
            self._pending_edit = None

    def _press(self, which: str, e: tk.Event) -> None:
        canvas = self.body if which == "body" else self.head
        canvas.focus_set()
        self._cancel_pending_edit()
        kind, payload, cy = self._find(which, e)
        info = {"which": which, "kind": kind, "payload": payload, "x": e.x, "y": e.y}
        if kind == "event" and which == "body" and not payload.all_day:
            col = self._column_at(canvas.canvasx(e.x))
            if col is not None:
                day0 = D.day_start(self._col_days[col])
                start_min = (max(payload.start, day0) - day0).total_seconds() / 60
                info["grab"] = cy / HOUR_H * 60 - start_min  # where inside the block the mouse went down
        self._press_info = info
        self._dragging = False

    def _motion(self, which: str, e: tk.Event) -> None:
        info = self._press_info
        if not info or info["kind"] != "event":
            return
        if not self._dragging:
            if abs(e.x - info["x"]) + abs(e.y - info["y"]) < 5:
                return  # a small wobble is still a click
            self._dragging = True
        self._draw_ghost(which, e)

    def _release(self, which: str, e: tk.Event) -> None:
        info = self._press_info
        if info is None:
            return
        if self._dragging:
            target = self._target(which, e)
            self._press_info, self._dragging = None, False
            self.body.delete("ghost")
            self.head.delete("ghost")
            if target:
                self._apply_move(*target)
            return
        self._press_info = None
        if info["kind"] == "event":
            occ = info["payload"]
            self._pending_edit = self.after(250, lambda: self._run_pending(occ))
        elif info["kind"] == "more":
            self.cursor = info["payload"]
            self.set_mode("day")

    def _run_pending(self, occ: Occurrence) -> None:
        self._pending_edit = None
        self.edit(occ)

    def _target(self, which: str, e: tk.Event):
        """(occurrence, new start) for where the dragged event would land, or None."""
        info = self._press_info
        if not info or info["kind"] != "event":
            return None
        occ = info["payload"]
        canvas = self.body if which == "body" else self.head
        cx, cy = canvas.canvasx(e.x), canvas.canvasy(e.y)
        if self.mode == "month":
            day = self._day_at(cx, cy)
            return None if day is None else (occ, occ.start + timedelta(days=(day - occ.start.date()).days))
        col = self._column_at(cx)
        if col is None:
            return None
        day = self._col_days[col]
        if occ.all_day or which == "head":
            return occ, occ.start + timedelta(days=(day - occ.start.date()).days)
        length = (occ.end - occ.start).total_seconds() / 60
        minutes = self._snap(cy / HOUR_H * 60 - info.get("grab", 0))
        minutes = max(0, min(minutes, max(0, 24 * 60 - int(length))))
        return occ, D.day_start(day) + timedelta(minutes=minutes)

    def _draw_ghost(self, which: str, e: tk.Event) -> None:
        canvas = self.body if which == "body" else self.head
        canvas.delete("ghost")
        target = self._target(which, e)
        if not target:
            return
        occ, new_start = target
        if self.mode == "month":
            for x0, y0, x1, y1, kind, payload in self._hits:
                if kind == "day" and payload == new_start.date():
                    canvas.create_rectangle(x0 + 2, y0 + 2, x1 - 2, y1 - 2, outline=T.ACCENT, width=2,
                                            dash=(4, 2), tags="ghost")
                    break
        elif which == "body" and self._col_days and new_start.date() in self._col_days:
            col = self._col_days.index(new_start.date())
            top = (new_start - D.day_start(new_start.date())).total_seconds() / 3600 * HOUR_H
            height = max((occ.end - occ.start).total_seconds() / 3600 * HOUR_H, 18)
            x0 = GUTTER + col * self._colw + 3
            canvas.create_rectangle(x0, top, x0 + self._colw - 6, top + height, outline=T.ACCENT, width=2,
                                    dash=(4, 2), tags="ghost")

    def _apply_move(self, occ: Occurrence, new_start: datetime) -> None:
        if new_start == occ.start:
            return
        ev = self.cal.get_event(occ.event.id)
        if ev is None:
            return
        if ev.source:
            messagebox.showinfo("Read-only",
                                "This event comes from a calendar link, so it can't be moved here. "
                                "Click it to read its details.", parent=self)
            return
        scope = "this"
        if ev.rrule:
            scope = ask_scope(self, "Move")
            if scope is None:
                return
        self.cal.move_occurrence(ev.id, occ.start, new_start, scope)


    def _double(self, which: str, e: tk.Event) -> None:
        self._cancel_pending_edit()
        kind, payload, y = self._find(which, e)
        if kind == "day":
            self.new_event(datetime.combine(payload, time(9, 0)))
        elif kind == "slot":
            minutes = int(y / HOUR_H * 60) // 30 * 30
            self.new_event(D.day_start(payload) + timedelta(minutes=min(minutes, 23 * 60)))
        elif kind == "allday":
            self.new_event(D.day_start(payload), all_day=True)

    def _wheel(self, e: tk.Event) -> None:
        if self.mode == "month":
            return
        up = getattr(e, "num", 0) == 4 or getattr(e, "delta", 0) > 0
        self.body.yview_scroll(-3 if up else 3, "units")

    # ---- actions ---------------------------------------------------------------------
    def new_event(self, start: datetime | None = None, all_day: bool = False) -> None:
        if start is None:
            first, last = self._range()
            today = date.today()
            day = today if first <= today < last else self.cursor
            if day == today:
                start = D.now().replace(minute=0, second=0) + timedelta(hours=1)
                if start.date() != today:  # late evening: keep it on today
                    start = datetime.combine(today, time(23, 0))
            else:
                start = datetime.combine(day, time(9, 0))
        EventDialog(self, self.cal, start=start, end=start + (timedelta(days=1) if all_day else timedelta(hours=1)),
                    all_day=all_day)

    def edit(self, occ: Occurrence) -> None:
        event = self.cal.get_event(occ.event.id)
        if event and event.source:  # linked events open for reading, never for editing
            ReadOnlyEventDialog(self, self.cal, event, occ)
            return
        if event:
            EventDialog(self, self.cal, event=event, occurrence=occ)

    def open_subscriptions(self) -> None:
        SubscriptionsWindow(self, self.cal)

    def manage_categories(self) -> None:
        CategoryDialog(self, self.cal)

    def import_ics(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Import calendar file",
                                          filetypes=[("iCalendar", "*.ics"), ("All files", "*.*")])
        if not path:
            return
        try:
            result = self.cal.import_ics(Path(path).read_text(encoding="utf-8-sig", errors="replace"))
        except Exception as exc:
            logging.getLogger(__name__).exception("Calendar import failed")
            messagebox.showerror("Import failed", f"That file couldn't be imported.\n\n{exc}", parent=self)
        else:
            messagebox.showinfo("Import finished", result.summary(), parent=self)

    def export_ics(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Export calendar", defaultextension=".ics",
                                            initialfile="cerealbox-calendar.ics", filetypes=[("iCalendar", "*.ics")])
        if path:
            Path(path).write_bytes(self.cal.export_ics().encode("utf-8"))
            messagebox.showinfo("Export finished", f"Saved to {path}", parent=self)


class SubscriptionDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, cal):
        super().__init__(parent)
        self.cal = cal
        self.title("Add calendar link")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.name_var, self.url_var, self.every_var = tk.StringVar(), tk.StringVar(), tk.StringVar(value="60")
        frm = ttk.Frame(self, padding=20)
        frm.pack()
        ttk.Label(frm, text="Add a calendar link", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="Paste the .ics or webcal link from Google, Apple or Outlook. CerealBox checks it on the "
                            "interval you choose. Events from a link are read-only here.",
                  style="Muted.TLabel", wraplength=460, justify="left").grid(row=1, column=0, columnspan=2,
                                                                             sticky="w", pady=(4, 12))
        rows = [("Name", ttk.Entry(frm, textvariable=self.name_var, width=40)),
                ("Link", ttk.Entry(frm, textvariable=self.url_var, width=40)),
                ("Check every (min)", ttk.Entry(frm, textvariable=self.every_var, width=8))]
        for i, (text, widget) in enumerate(rows, start=2):
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=i, column=0, sticky="e", padx=(0, 12), pady=5)
            widget.grid(row=i, column=1, sticky="w", pady=5)
        btns = ttk.Frame(frm)
        btns.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="Save and sync", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _save(self) -> None:
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValueError("Give the calendar a name.")
            url = normalize_url(self.url_var.get())
            every = int(self.every_var.get() or 60)
            if every < 5:
                raise ValueError("Check at least every 5 minutes.")
        except ValueError as exc:
            messagebox.showerror("Check the link", str(exc), parent=self)
            return
        sub = Subscription.new(name, url, every)
        self.cal.save_subscription(sub)
        self.cal.start_sync(sub.id)
        self.destroy()


class SubscriptionsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, cal):
        super().__init__(parent)
        self.cal = cal
        self.title("Calendar links")
        self.configure(bg=T.BG)
        frm = ttk.Frame(self, padding=20)
        frm.pack()
        ttk.Label(frm, text="Calendar links", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Keep calendars from Google, Apple or Outlook up to date. Their events are read-only here.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        self.tree = ttk.Treeview(frm, columns=("name", "every", "status"), show="headings", height=8,
                                 selectmode="browse")
        for key, text, width in (("name", "Name", 190), ("every", "Every", 90), ("status", "Status", 340)):
            self.tree.heading(key, text=text, anchor="w")
            self.tree.column(key, width=width, anchor="w")
        self.tree.tag_configure("problem", foreground=T.NOW)
        self.tree.pack(fill="x")
        row = ttk.Frame(frm)
        row.pack(fill="x", pady=8)
        ttk.Button(row, text="Add link", style="Accent.TButton", command=self.add).pack(side="left")
        ttk.Button(row, text="Sync now", command=self.sync_now).pack(side="left", padx=6)
        ttk.Button(row, text="Remove", style="Danger.TButton", command=self.remove).pack(side="left")
        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e", pady=(10, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self._subs = [("calendar.subscriptions.changed", self._refresh), ("calendar.synced", self._refresh)]
        for pattern, handler in self._subs:
            cal.api.on(pattern, handler)
        self.bind("<Destroy>", self._cleanup, add="+")
        self._refresh()
        _modal(self, parent)

    def _cleanup(self, event) -> None:
        if event.widget is self:
            for pattern, handler in self._subs:
                self.cal.api.off(pattern, handler)

    @staticmethod
    def _status(s: Subscription) -> str:
        if s.last_error:
            return f"Problem: {s.last_error[:60]}"
        if s.last_sync:
            return f"Up to date · checked {s.last_sync:%b %d, %H:%M}"
        return "Checking…" if s.last_attempt else "Not checked yet"

    def _refresh(self, *_a, **_k) -> None:
        if not self.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        for s in self.cal.subscriptions():
            self.tree.insert("", "end", iid=s.id, tags=("problem",) if s.last_error else (),
                             values=(s.name, f"{s.interval_min} min", self._status(s)))

    def add(self) -> None:
        SubscriptionDialog(self, self.cal)

    def sync_now(self) -> None:
        sel = self.tree.selection()
        if sel:
            self.cal.start_sync(sel[0])

    def remove(self) -> None:
        sel = self.tree.selection()
        if sel and messagebox.askyesno("Remove link", "Remove this calendar link and its events?", parent=self):
            self.cal.remove_subscription(sel[0])
