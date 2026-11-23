"""Dialogs for the calendar: the event editor, the 'this one or all?' prompt, the category manager."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import colorchooser, messagebox, ttk

from ...core import dates as D
from ...core.ids import new_id
from ...ui import theme as T
from .models import DEFAULT_COLOR, IMPORT_PALETTE, Category, Event, Occurrence
from .recurrence import WEEKDAY_CODES, build_rrule, describe_rrule, parse_rrule

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


def _modal(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.transient(parent.winfo_toplevel())
    T.center(win, parent)
    win.wait_visibility()
    win.grab_set()


def ask_scope(parent: tk.Misc, verb: str) -> str | None:
    """'this' | 'all' | None (cancelled) for edits/deletes of a repeating event."""
    dlg = tk.Toplevel(parent)
    dlg.title(f"{verb} repeating event")
    dlg.configure(bg=T.BG)
    dlg.resizable(False, False)
    result: dict[str, str | None] = {"v": None}

    def pick(v: str) -> None:
        result["v"] = v
        dlg.destroy()

    frm = ttk.Frame(dlg, padding=20)
    frm.pack()
    ttk.Label(frm, text=f"{verb} which events?", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
    ttk.Button(frm, text="Only this event", command=lambda: pick("this")).pack(fill="x", pady=3)
    ttk.Button(frm, text="All events in the series", command=lambda: pick("all")).pack(fill="x", pady=3)
    ttk.Button(frm, text="Cancel", command=dlg.destroy).pack(fill="x", pady=(10, 0))
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    _modal(dlg, parent)
    dlg.wait_window()
    return result["v"]


class EventDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, cal, event: Event | None = None, occurrence: Occurrence | None = None,
                 start: datetime | None = None, end: datetime | None = None, all_day: bool = False):
        super().__init__(parent)
        self.cal, self.event, self.occ = cal, event, occurrence
        self.title("Edit event" if event else "New event")
        self.configure(bg=T.BG)
        self.resizable(False, False)

        if event:
            s = occurrence.start if occurrence else event.start
            e = occurrence.end if occurrence else event.end
            all_day = event.all_day
        else:
            s = start or D.now().replace(minute=0, second=0) + timedelta(hours=1)
            e = end or s + (timedelta(days=1) if all_day else timedelta(hours=1))
        self._start0 = s
        shown_end = (e - timedelta(days=1) if e > s else s) if all_day else e

        self.title_var = tk.StringVar(value=event.title if event else "")
        self.all_day_var = tk.BooleanVar(value=all_day)
        self.sd, self.st = tk.StringVar(value=_date_text(s)), tk.StringVar(value=D.fmt_time(s))
        self.ed, self.et = tk.StringVar(value=_date_text(shown_end)), tk.StringVar(value=D.fmt_time(shown_end))
        self.loc_var = tk.StringVar(value=event.location if event else "")
        reminders = event.reminders if event else ([] if all_day else [15])
        self.rem_var = tk.StringVar(value=", ".join(_compact_minutes(m) for m in reminders))

        frm = ttk.Frame(self, padding=20)
        frm.pack()
        self.frm = frm

        def row_label(text: str, row: int) -> None:
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="ne", padx=(0, 14), pady=6)

        row_label("Title", 0)
        self.title_entry = ttk.Entry(frm, textvariable=self.title_var, width=48)
        self.title_entry.grid(row=0, column=1, columnspan=3, sticky="ew")

        # category
        row_label("Category", 1)
        self.cat_ids: dict[str, str | None] = {NO_CATEGORY: None}
        for c in cal.categories():
            self.cat_ids[c.name] = c.id
        current = cal.category(event.category_id) if event else None
        self.cat_var = tk.StringVar(value=current.name if current else NO_CATEGORY)
        combo = ttk.Combobox(frm, textvariable=self.cat_var, values=list(self.cat_ids), state="readonly", width=22)
        combo.grid(row=1, column=1, columnspan=2, sticky="w")
        self.swatch = tk.Label(frm, width=3, bg=DEFAULT_COLOR)
        self.swatch.grid(row=1, column=3, sticky="w", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._update_swatch())
        self._update_swatch()

        # when
        ttk.Checkbutton(frm, text="All day", variable=self.all_day_var, command=self._on_all_day).grid(
            row=2, column=1, columnspan=3, sticky="w", pady=(6, 0))
        row_label("Starts", 3)
        ttk.Entry(frm, textvariable=self.sd, width=13).grid(row=3, column=1, sticky="w", pady=3)
        self.st_entry = ttk.Entry(frm, textvariable=self.st, width=10)
        self.st_entry.grid(row=3, column=2, sticky="w", padx=(8, 0))
        row_label("Ends", 4)
        ttk.Entry(frm, textvariable=self.ed, width=13).grid(row=4, column=1, sticky="w", pady=3)
        self.et_entry = ttk.Entry(frm, textvariable=self.et, width=10)
        self.et_entry.grid(row=4, column=2, sticky="w", padx=(8, 0))

        # repeat
        row_label("Repeat", 5)
        choices = REPEAT_CHOICES + ([CUSTOM] if event and event.rrule and parse_rrule(event.rrule).custom else [])
        self.rep_var = tk.StringVar(value=NO_REPEAT)
        rep = ttk.Combobox(frm, textvariable=self.rep_var, values=choices, state="readonly", width=22)
        rep.grid(row=5, column=1, columnspan=2, sticky="w")
        self.rep_note = ttk.Label(frm, text="", style="Muted.TLabel")
        self.rep_note.grid(row=5, column=3, sticky="w", padx=8)
        self._build_repeat_options(frm, row=6)
        rep.bind("<<ComboboxSelected>>", lambda _e: self._on_repeat_change())
        self._load_repeat(event.rrule if event else None)

        row_label("Reminders", 7)
        ttk.Entry(frm, textvariable=self.rem_var, width=22).grid(row=7, column=1, columnspan=2, sticky="w", pady=3)
        ttk.Label(frm, text="before the start, e.g. 15, 1h, 1d", style="Muted.TLabel").grid(
            row=7, column=3, sticky="w", padx=8)
        row_label("Location", 8)
        ttk.Entry(frm, textvariable=self.loc_var, width=48).grid(row=8, column=1, columnspan=3, sticky="ew", pady=3)
        row_label("Notes", 9)
        self.notes = tk.Text(frm, width=48, height=4, wrap="word", relief="flat", highlightthickness=1,
                             highlightbackground=T.LINE, highlightcolor=T.ACCENT, font=(T.FAMILY, 10), padx=6, pady=4)
        self.notes.grid(row=9, column=1, columnspan=3, sticky="ew", pady=3)
        if event:
            self.notes.insert("1.0", event.notes)

        # buttons
        btns = ttk.Frame(frm)
        btns.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        if event:
            ttk.Button(btns, text="Delete", style="Danger.TButton", command=self._delete).pack(side="left")
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.title_entry.bind("<Return>", lambda _e: self._save())
        self._on_all_day()
        self._on_repeat_change()
        _modal(self, parent)
        self.title_entry.focus_set()
        self.title_entry.select_range(0, "end")

    # ---- repeat controls ------------------------------------------------------------------
    def _build_repeat_options(self, frm: ttk.Frame, row: int) -> None:
        self.rep_opts = opts = ttk.Frame(frm)
        opts.grid(row=row, column=1, columnspan=3, sticky="w", pady=(2, 4))
        self.interval_var, self.count_var = tk.StringVar(value="1"), tk.StringVar(value="10")
        self.until_var, self.end_mode = tk.StringVar(), tk.StringVar(value="never")
        self.day_vars = {code: tk.BooleanVar() for code, _ in WEEK_ORDER}

        every = ttk.Frame(opts)
        every.grid(row=0, column=0, sticky="w")
        ttk.Label(every, text="Every").pack(side="left")
        ttk.Spinbox(every, from_=1, to=99, width=4, textvariable=self.interval_var).pack(side="left", padx=6)
        self.unit_lbl = ttk.Label(every, text="week(s)")
        self.unit_lbl.pack(side="left")

        self.days_frame = ttk.Frame(opts)
        self.days_frame.grid(row=1, column=0, sticky="w", pady=4)
        for code, label in WEEK_ORDER:
            ttk.Checkbutton(self.days_frame, text=label, variable=self.day_vars[code]).pack(side="left", padx=(0, 6))

        ends = ttk.Frame(opts)
        ends.grid(row=2, column=0, sticky="w")
        ttk.Label(ends, text="Ends").pack(side="left", padx=(0, 6))
        ttk.Radiobutton(ends, text="Never", value="never", variable=self.end_mode).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(ends, text="After", value="count", variable=self.end_mode).pack(side="left")
        ttk.Entry(ends, textvariable=self.count_var, width=4).pack(side="left", padx=4)
        ttk.Label(ends, text="times").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(ends, text="On", value="until", variable=self.end_mode).pack(side="left")
        ttk.Entry(ends, textvariable=self.until_var, width=11).pack(side="left", padx=4)

    def _load_repeat(self, rule: str | None) -> None:
        if not rule:
            return
        p = parse_rrule(rule)
        if p.custom:
            self.rep_var.set(CUSTOM)
            self.rep_note.config(text=describe_rrule(rule))
            return
        self.rep_var.set(CHOICE_OF[p.freq])
        self.interval_var.set(str(p.interval))
        for code in p.byday:
            self.day_vars[code].set(True)
        if p.count:
            self.end_mode.set("count")
            self.count_var.set(str(p.count))
        elif p.until:
            self.end_mode.set("until")
            self.until_var.set(f"{p.until.month}/{p.until.day}/{p.until.year}")

    def _on_repeat_change(self) -> None:
        choice = self.rep_var.get()
        if choice in (NO_REPEAT, CUSTOM):
            self.rep_opts.grid_remove()
            return
        self.rep_opts.grid()
        self.unit_lbl.config(text=UNIT_OF[choice])
        if choice == "Weekly":
            self.days_frame.grid()
            if not any(v.get() for v in self.day_vars.values()):
                try:
                    start = D.parse_date(self.sd.get())
                except ValueError:
                    start = self._start0.date()
                self.day_vars[WEEKDAY_CODES[start.weekday()]].set(True)
        else:
            self.days_frame.grid_remove()

    def _on_all_day(self) -> None:
        state = ["disabled"] if self.all_day_var.get() else ["!disabled"]
        self.st_entry.state(state)
        self.et_entry.state(state)

    def _update_swatch(self) -> None:
        cat = self.cal.category(self.cat_ids.get(self.cat_var.get()))
        self.swatch.config(bg=cat.color if cat else DEFAULT_COLOR)

    # ---- reading the form ---------------------------------------------------------------------
    def _collect(self) -> dict:
        title = self.title_var.get().strip()
        if not title:
            raise ValueError("Give the event a title.")
        all_day = self.all_day_var.get()
        sd, ed = D.parse_date(self.sd.get()), D.parse_date(self.ed.get())
        if all_day:
            start, end = D.day_start(sd), D.day_start(ed) + timedelta(days=1)
            if end <= start:
                raise ValueError("The end date is before the start date.")
        else:
            start = datetime.combine(sd, D.parse_time(self.st.get()))
            end = datetime.combine(ed, D.parse_time(self.et.get()))
            if end < start:
                raise ValueError("The event ends before it starts.")
        return {
            "title": title, "start": start, "end": end, "all_day": all_day,
            "category_id": self.cat_ids.get(self.cat_var.get()),
            "location": self.loc_var.get().strip(),
            "notes": self.notes.get("1.0", "end").strip(),
            "reminders": D.parse_minute_list(self.rem_var.get()),
            "rrule": self._collect_rrule(start),
        }

    def _collect_rrule(self, start: datetime) -> str | None:
        choice = self.rep_var.get()
        if choice == NO_REPEAT:
            return None
        if choice == CUSTOM:
            return self.event.rrule
        try:
            interval = int(self.interval_var.get())
            if interval < 1:
                raise ValueError
        except ValueError:
            raise ValueError("'Every' needs a whole number, 1 or more.") from None
        byday = []
        if choice == "Weekly":
            byday = [c for c, _ in WEEK_ORDER if self.day_vars[c].get()] or [WEEKDAY_CODES[start.weekday()]]
        count = until = None
        mode = self.end_mode.get()
        if mode == "count":
            try:
                count = int(self.count_var.get())
                if count < 1:
                    raise ValueError
            except ValueError:
                raise ValueError("'After … times' needs a whole number, 1 or more.") from None
        elif mode == "until":
            until = D.parse_date(self.until_var.get())
            if until < start.date():
                raise ValueError("The repeat end date is before the event starts.")
        return build_rrule(FREQ_OF[choice], interval, byday, count, until)

    # ---- actions ------------------------------------------------------------------------------
    def _scope(self, verb: str) -> str | None:
        scope = ask_scope(self, verb)
        if self.winfo_exists():
            self.grab_set()  # the sub-dialog released our grab when it closed
        return scope

    def _save(self) -> None:
        try:
            data = self._collect()
        except ValueError as exc:
            messagebox.showerror("Check the event details", str(exc), parent=self)
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
            else:  # "all": shift the whole series by however far this occurrence moved
                delta = data["start"] - occ_start
                master = ev.copy()
                master.start = ev.start + delta
                master.exdates = [x + delta for x in ev.exdates]
                data = {**data, "end": master.start + (data["end"] - data["start"]), "start": master.start}
                self._apply(master, data)
        self.destroy()

    def _apply(self, ev: Event, data: dict) -> None:
        for key, value in data.items():
            setattr(ev, key, value)
        self.cal.save_event(ev)

    def _delete(self) -> None:
        ev = self.event
        if not ev.is_recurring:
            if not messagebox.askyesno("Delete event", f"Delete “{ev.title}”?", parent=self):
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
        self.destroy()


class CategoryDialog(tk.Toplevel):
    """Rename, recolour, add and delete categories. Nothing is saved until you press Save."""

    def __init__(self, parent: tk.Misc, cal):
        super().__init__(parent)
        self.cal = cal
        self.title("Categories")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.rows: list[dict] = []
        self.removed: list[str] = []

        frm = ttk.Frame(self, padding=20)
        frm.pack()
        ttk.Label(frm, text="Categories", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frm, text="Click a colour to change it. Events in a deleted category become uncategorised.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        self.list_frame = ttk.Frame(frm)
        self.list_frame.pack(fill="x")
        for cat in cal.categories():
            self._add_row(cat)
        ttk.Button(frm, text="Add category", command=self._add_new).pack(anchor="w", pady=(10, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(14, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        _modal(self, parent)

    def _add_row(self, cat: Category) -> None:
        frame = ttk.Frame(self.list_frame)
        frame.pack(fill="x", pady=3)
        row = {"id": cat.id, "name": tk.StringVar(value=cat.name), "color": cat.color, "frame": frame}
        swatch = tk.Label(frame, width=4, bg=cat.color, cursor="hand2")
        swatch.pack(side="left", padx=(0, 10))
        swatch.bind("<Button-1>", lambda _e, r=row, s=swatch: self._pick(r, s))
        ttk.Entry(frame, textvariable=row["name"], width=28).pack(side="left")
        ttk.Button(frame, text="Delete", style="Danger.TButton", command=lambda r=row: self._remove(r)).pack(
            side="left", padx=8)
        self.rows.append(row)

    def _add_new(self) -> None:
        color = IMPORT_PALETTE[len(self.rows) % len(IMPORT_PALETTE)]
        self._add_row(Category(new_id("cat"), "New category", color))
        self.rows[-1]["new"] = True

    def _pick(self, row: dict, swatch: tk.Label) -> None:
        _rgb, hexval = colorchooser.askcolor(color=row["color"], parent=self, title="Category colour")
        if hexval:
            row["color"] = hexval
            swatch.config(bg=hexval)

    def _remove(self, row: dict) -> None:
        if not row.get("new"):
            self.removed.append(row["id"])
        row["frame"].destroy()
        self.rows.remove(row)

    def _save(self) -> None:
        names = [r["name"].get().strip() for r in self.rows]
        if any(not n for n in names):
            return messagebox.showerror("Check the categories", "Every category needs a name.", parent=self)
        if len({n.lower() for n in names}) != len(names):
            return messagebox.showerror("Check the categories", "Two categories have the same name.", parent=self)
        with self.cal.api.vault.batch():
            for cat_id in self.removed:
                self.cal.delete_category(cat_id)
            for row, name in zip(self.rows, names, strict=False):
                self.cal.save_category(Category(row["id"], name, row["color"]))
        self.destroy()
        return None


class ReadOnlyEventDialog(tk.Toplevel):
    """Shows everything about an event that comes from a calendar link. Nothing here can be changed."""

    def __init__(self, parent: tk.Misc, cal, event: Event, occurrence: Occurrence | None = None):
        super().__init__(parent)
        self.title(event.title)
        self.configure(bg=T.BG)
        self.resizable(False, False)
        start = occurrence.start if occurrence else event.start
        end = occurrence.end if occurrence else event.end
        when = (f"{D.fmt_date_long(start.date())} · all day" if event.all_day else
                f"{D.fmt_date_long(start.date())}\n{D.fmt_time(start)} – {D.fmt_time(end)}")
        source = next((s for s in cal.subscriptions() if s.id == event.source), None)
        category = cal.category(event.category_id)

        frm = ttk.Frame(self, padding=(28, 24, 28, 20))
        frm.pack()
        ttk.Label(frm, text=event.title, style="Display.TLabel", wraplength=460).pack(anchor="w")
        ttk.Label(frm, text=when, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(8, 0))
        if event.rrule:
            ttk.Label(frm, text=describe_rrule(event.rrule), style="Muted.TLabel").pack(anchor="w")
        rows = []
        if event.location:
            rows.append(("Where", event.location))
        if category:
            rows.append(("Category", category.name))
        if event.reminders:
            rows.append(("Reminders", ", ".join(D.fmt_minutes(m) for m in event.reminders) + " before"))
        for label, value in rows:
            line = ttk.Frame(frm)
            line.pack(anchor="w", pady=(14, 0), fill="x")
            ttk.Label(line, text=label, style="Muted.TLabel", width=11).pack(side="left", anchor="n")
            ttk.Label(line, text=value, wraplength=380, justify="left").pack(side="left", anchor="w")
        if event.notes:
            ttk.Label(frm, text="Notes", style="Muted.TLabel").pack(anchor="w", pady=(16, 2))
            ttk.Label(frm, text=event.notes, wraplength=460, justify="left").pack(anchor="w")

        name = f"“{source.name}”" if source else "a calendar link"
        ttk.Label(frm, text=f"From {name}. It refreshes automatically, so changes are made in the source calendar.",
                  style="Muted.TLabel", wraplength=460, justify="left").pack(anchor="w", pady=(20, 0))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="Close", style="Accent.TButton", command=self.destroy).pack(side="right")
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", lambda _e: self.destroy())
        _modal(self, parent)
