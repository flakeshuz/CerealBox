"""Tasks screen: filtered list, quick complete, search, and an editor with repeat and reminders."""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ...core import dates as D
from ...core.rrule import FREQ_BY_LABEL as FREQ
from ...core.rrule import LABEL_BY_FREQ as CHOICE_OF_FREQ
from ...core.rrule import (
    REPEAT_CHOICES,
    REPEAT_NONE,
    WEEKDAY_CODES,
    build_rrule,
    parse_rrule,
)
from ...core.rrule import REPEAT_CUSTOM as CUSTOM
from ...ui import theme as T
from . import is_overdue
from .models import PRIORITY_CODES, PRIORITY_NAMES, Task

VIEW_LABELS = (("open", "Open"), ("today", "Today"), ("done", "Done"), ("all", "All"))


def fmt_due(t: Task, now: datetime) -> str:
    if not t.due:
        return ""
    d = t.due.date()
    day = {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get((d - now.date()).days) or f"{d:%a %b} {d.day}"
    return f"{day} {D.fmt_time(t.due)}" if t.has_time else day


def _modal(win: tk.Toplevel, parent: tk.Misc) -> None:
    win.transient(parent.winfo_toplevel())
    T.center(win, parent)
    win.wait_visibility()
    win.grab_set()


class TasksView(ttk.Frame):
    def __init__(self, parent: tk.Misc, mod):
        super().__init__(parent)
        self.mod = mod
        self.view = tk.StringVar(value="open")
        self.search = tk.StringVar()

        bar = ttk.Frame(self, padding=(14, 12, 14, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Tasks", style="Title.TLabel").pack(side="left", padx=(0, 16))
        for key, label in VIEW_LABELS:
            ttk.Radiobutton(bar, text=label, value=key, variable=self.view, style="Segment.Toolbutton",
                            command=self.refresh).pack(side="left", padx=(0, 0))
        ttk.Button(bar, text="New task", style="Accent.TButton", command=self.new).pack(side="right")
        ttk.Entry(bar, textvariable=self.search, width=24).pack(side="right", padx=10)
        self.search.trace_add("write", lambda *_: self.refresh())

        act = ttk.Frame(self, padding=(14, 0, 14, 8))
        act.pack(fill="x")
        self.toggle_btn = ttk.Button(act, text="Complete", command=self.toggle_selected)
        self.toggle_btn.pack(side="left")
        self.edit_btn = ttk.Button(act, text="Edit", command=self.edit_selected)
        self.edit_btn.pack(side="left", padx=6)
        ttk.Button(act, text="Delete", style="Danger.TButton", command=self.delete_selected).pack(side="left")
        self.status = ttk.Label(act, style="Muted.TLabel")
        self.status.pack(side="right")

        self.schedule = ttk.Label(self, text="", style="Muted.TLabel", justify="left", wraplength=900,
                                  padding=(14, 0, 14, 8))
        self.schedule.pack(fill="x")

        body = ttk.Frame(self, padding=(14, 0, 14, 14))
        body.pack(fill="both", expand=True)
        cols = ("done", "title", "due", "priority", "tags")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", selectmode="extended")
        for col, text, width, stretch in (("done", "", 40, False), ("title", "Task", 360, True),
                                          ("due", "Due", 160, False), ("priority", "Priority", 90, False),
                                          ("tags", "Tags", 200, True)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, stretch=stretch, anchor="w")
        self.tree.tag_configure("overdue", foreground=T.NOW)
        self.tree.tag_configure("done", foreground=T.FAINT)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.empty = ttk.Label(body, style="Muted.TLabel", justify="center")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())
        self.tree.bind("<Return>", lambda _e: self.edit_selected())
        self.tree.bind("<space>", lambda _e: self.toggle_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.bind("<BackSpace>", lambda _e: self.delete_selected())

        self._subs = [("tasks.*", self._on_change), ("calendar.*", self._on_change), ("vault.reloaded", self._on_change)]
        for pattern, handler in self._subs:
            mod.api.on(pattern, handler)
        self._timer = None
        self._tick_timer()
        self.bind("<Destroy>", self._cleanup, add="+")
        self.refresh()

    # ---- refresh ----------------------------------------------------------------------------
    def _on_change(self, topic: str = "", **_) -> None:
        self.refresh()

    def _cleanup(self, event) -> None:
        if event.widget is not self:
            return
        for pattern, handler in self._subs:
            self.mod.api.off(pattern, handler)
        if self._timer:
            self.after_cancel(self._timer)

    def _tick(self) -> None:
        self.refresh()  # keeps the overdue colouring and "Today" labels current
        self._tick_timer()

    def _tick_timer(self) -> None:
        self._timer = self.after(60_000, self._tick)

    def refresh(self) -> None:
        now = D.now()
        self.tree.delete(*self.tree.get_children())
        for t in self.mod.list(self.view.get(), self.search.get(), now):
            tags = ("done",) if t.done else (("overdue",) if is_overdue(t, now) else ())
            title = t.title + ("  ↻" if t.rrule else "")
            self.tree.insert("", "end", iid=t.id, tags=tags, values=(
                "✓" if t.done else "○", title, fmt_due(t, now), PRIORITY_NAMES[t.priority], ", ".join(t.tags)))
        if not self.tree.get_children():
            self.empty.config(text=self._empty_text())
            self.empty.place(relx=0.5, rely=0.42, anchor="center")
        else:
            self.empty.place_forget()
        open_now = self.mod.list("open", "", now)
        overdue = sum(1 for t in open_now if is_overdue(t, now))
        if self.view.get() == "today":
            count, label = len(self.mod.list("today", "", now)), "to do today or earlier"
        else:
            count, label = len(open_now), "open"
        self.status.config(text=f"{count} {label}" + (f"  ·  {overdue} overdue" if overdue else ""))
        self._refresh_schedule(now)
        self._update_buttons()

    def _empty_text(self) -> str:
        if self.search.get().strip():
            return f"No tasks match “{self.search.get().strip()}”."
        return {"open": "Nothing open. Enjoy the quiet.", "today": "Nothing due today.",
                "done": "Nothing finished yet.",
                "all": "No tasks yet. Press Ctrl+N to add one."}[self.view.get()]

    def _refresh_schedule(self, now: datetime) -> None:
        if self.view.get() != "today" or not self.mod.api.has_service("calendar.events_between"):
            self.schedule.config(text="")
            return
        day = D.day_start(now.date())
        rows = self.mod.api.call("calendar.events_between", day, day + timedelta(days=1))
        if not rows:
            self.schedule.config(text="Nothing on the calendar today.")
            return
        lines = [f"{'All day' if r['all_day'] else D.fmt_time(r['start'])}   {r['title']}" for r in rows[:5]]
        if len(rows) > 5:
            lines.append(f"+{len(rows) - 5} more")
        self.schedule.config(text="On the calendar today:\n" + "\n".join(lines))

    def _update_buttons(self) -> None:
        sel = self.tree.selection()
        self.edit_btn.state(["!disabled"] if len(sel) == 1 else ["disabled"])
        if len(sel) == 1:
            t = self.mod.get(sel[0])
            self.toggle_btn.config(text="Reopen" if t and t.done else "Complete")
        else:
            self.toggle_btn.config(text="Complete")
        self.toggle_btn.state(["!disabled"] if sel else ["disabled"])

    # ---- actions ------------------------------------------------------------------------------
    def new(self) -> None:
        TaskDialog(self, self.mod)

    def edit_selected(self) -> None:
        sel = self.tree.selection()
        if len(sel) == 1:
            t = self.mod.get(sel[0])
            if t:
                TaskDialog(self, self.mod, t)

    def toggle_selected(self) -> None:
        for iid in self.tree.selection():
            self.mod.toggle(iid)

    def delete_selected(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        msg = "Delete this task?" if len(sel) == 1 else f"Delete {len(sel)} tasks?"
        if messagebox.askyesno("Delete", msg, parent=self):
            for iid in sel:
                self.mod.delete(iid)


class TaskDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, mod, task: Task | None = None):
        super().__init__(parent)
        self.mod, self.task = mod, task
        self.title("Edit task" if task else "New task")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        t = task

        self.title_var = tk.StringVar(value=t.title if t else "")
        self.date_var = tk.StringVar(value=f"{t.due.month}/{t.due.day}/{t.due.year}" if t and t.due else "")
        self.time_var = tk.StringVar(value=D.fmt_time(t.due) if t and t.has_time else "")
        self.pri_var = tk.StringVar(value=PRIORITY_NAMES[t.priority if t else 2])
        self.tags_var = tk.StringVar(value=", ".join(t.tags) if t else "")
        self.rem_var = tk.StringVar(value=", ".join(D.compact_minutes(m) for m in t.reminders) if t else "")
        self.rep_var = tk.StringVar(value=REPEAT_NONE)
        self._loaded_rep = REPEAT_NONE
        if t and t.rrule:
            p = parse_rrule(t.rrule)
            self._loaded_rep = CUSTOM if p.custom else CHOICE_OF_FREQ.get(p.freq, REPEAT_NONE)
            self.rep_var.set(self._loaded_rep)
        choices = REPEAT_CHOICES + ([CUSTOM] if self._loaded_rep == CUSTOM else [])

        frm = ttk.Frame(self, padding=20)
        frm.pack()

        def label(text: str, row: int) -> None:
            ttk.Label(frm, text=text, style="Muted.TLabel").grid(row=row, column=0, sticky="ne", padx=(0, 14), pady=6)

        label("Task", 0)
        self.title_entry = ttk.Entry(frm, textvariable=self.title_var, width=46)
        self.title_entry.grid(row=0, column=1, columnspan=3, sticky="ew")
        label("Due", 1)
        ttk.Entry(frm, textvariable=self.date_var, width=14).grid(row=1, column=1, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=self.time_var, width=10).grid(row=1, column=2, sticky="w", padx=(8, 0))
        ttk.Label(frm, text="date and optional time", style="Muted.TLabel").grid(row=1, column=3, sticky="w", padx=8)
        label("Repeat", 2)
        self.rep_combo = ttk.Combobox(frm, textvariable=self.rep_var, values=choices, state="readonly", width=22)
        self.rep_combo.grid(row=2, column=1, columnspan=2, sticky="w", pady=3)
        label("Priority", 3)
        self.pri_combo = ttk.Combobox(frm, textvariable=self.pri_var, values=list(PRIORITY_CODES), state="readonly",
                                      width=22)
        self.pri_combo.grid(row=3, column=1, columnspan=2, sticky="w", pady=3)
        label("Tags", 4)
        ttk.Entry(frm, textvariable=self.tags_var, width=46).grid(row=4, column=1, columnspan=3, sticky="ew", pady=3)
        label("Reminders", 5)
        ttk.Entry(frm, textvariable=self.rem_var, width=22).grid(row=5, column=1, columnspan=2, sticky="w", pady=3)
        ttk.Label(frm, text="needs a time, e.g. 15, 1h", style="Muted.TLabel").grid(row=5, column=3, sticky="w", padx=8)
        label("Notes", 6)
        self.notes = tk.Text(frm, width=46, height=4, wrap="word", relief="flat", highlightthickness=1,
                             highlightbackground=T.LINE, highlightcolor=T.ACCENT, font=(T.FAMILY, 10), padx=6, pady=4)
        self.notes.grid(row=6, column=1, columnspan=3, sticky="ew", pady=3)
        if t:
            self.notes.insert("1.0", t.notes)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=self._save).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Control-Return>", lambda _e: self._save())
        self.title_entry.bind("<Return>", lambda _e: self._save())
        _modal(self, parent)
        self.title_entry.focus_set()

    def _collect(self) -> dict:
        title = self.title_var.get().strip()
        if not title:
            raise ValueError("Give the task a name.")
        dstr, tstr = self.date_var.get().strip(), self.time_var.get().strip()
        has_time, due = False, None
        if dstr:
            d = D.parse_date(dstr)
            if tstr:
                due, has_time = datetime.combine(d, D.parse_time(tstr)), True
            else:
                due = D.day_start(d)
        elif tstr:
            raise ValueError("Add a due date as well as a time.")
        reminders = D.parse_minute_list(self.rem_var.get()) if self.rem_var.get().strip() else []
        if reminders and not has_time:
            raise ValueError("Reminders need a due time.")
        rep = self.rep_var.get()
        rrule = None
        if rep != REPEAT_NONE:
            if due is None:
                raise ValueError("A repeating task needs a due date.")
            if rep == CUSTOM:
                rrule = self.task.rrule
            elif rep == self._loaded_rep and self.task and self.task.rrule and \
                    (self.task.due is None or self.task.due.weekday() == due.weekday()):
                rrule = self.task.rrule  # unchanged repeat: keep its end date or count
            else:
                # Changing the repeat type or the weekday: rebuild, but keep the interval and any end date/count
                keep = parse_rrule(self.task.rrule) if self.task and self.task.rrule else None
                byday = [WEEKDAY_CODES[due.weekday()]] if rep == "Weekly" else []
                rrule = build_rrule(FREQ[rep], interval=keep.interval if keep else 1, byday=byday,
                                    count=keep.count if keep else None, until=keep.until if keep else None)
        return {
            "title": title, "due": due, "has_time": has_time, "rrule": rrule, "reminders": reminders,
            "priority": PRIORITY_CODES[self.pri_var.get()],
            "tags": [x.strip() for x in self.tags_var.get().split(",") if x.strip()],
            "notes": self.notes.get("1.0", "end").strip(),
        }

    def _save(self) -> None:
        try:
            data = self._collect()
        except ValueError as exc:
            messagebox.showerror("Check the task", str(exc), parent=self)
            return
        t = self.task.copy() if self.task else Task.new(data["title"])
        if self.task is None or data["due"] != t.due:
            t.series_start = data["due"] if data["rrule"] else None  # a moved repeat restarts from the new date
        for k, v in data.items():
            setattr(t, k, v)
        self.mod.save(t)
        self.destroy()
