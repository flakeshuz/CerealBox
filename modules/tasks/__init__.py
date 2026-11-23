"""Tasks module: to-dos with due dates, priorities, tags, repeats and reminders.

Other modules can use it through services:
    api.call("tasks.add", "Pay Q4 estimated tax", due=datetime(2027, 1, 15), has_time=False, tags=["taxes"])
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ...core import dates as D
from ...core.api import Reminder
from ...core.rrule import compile_rule
from ..base import Module
from .models import Task

VIEWS = ("open", "today", "done", "all")


def is_overdue(t: Task, now: datetime) -> bool:
    if t.done or not t.due:
        return False
    return t.due < now if t.has_time else t.due.date() < now.date()


def _sort_key(t: Task):
    return (t.done, t.due is None, t.due or datetime.max, t.priority, t.title.lower())


class TasksModule(Module):
    name = "tasks"
    title = "Tasks"

    # ---- lifecycle -----------------------------------------------------------------------
    def setup(self) -> None:
        self._col = self.col("items")
        self._load()
        self.api.on("vault.reloaded", lambda **_: self._load())

    def _load(self) -> None:
        self._tasks = {d["id"]: Task.from_dict(d) for d in self._col.all()}

    def services(self):
        return {
            "add": self.add_task,
            "open_tasks": lambda: self.list("open"),
            "due_today": lambda: self.list("today"),
            "reminders_due": self.due_reminders,
            "complete": self.complete,
        }

    def complete(self, task_id: str) -> Task | None:
        """Tick a task off (no-op if it's already done). Repeating tasks move on to their next date."""
        t = self.get(task_id)
        return self.toggle(task_id) if t and not t.done else t

    def create_view(self, parent):
        from .ui import TasksView  # imported lazily so the engine works without tkinter

        return TasksView(parent, self)

    # ---- reads -----------------------------------------------------------------------------
    def get(self, task_id: str) -> Task | None:
        t = self._tasks.get(task_id)
        return t.copy() if t else None

    def list(self, view: str = "open", search: str = "", now: datetime | None = None) -> list[Task]:
        now = now or D.now()
        today = now.date()
        q = search.strip().lower()
        out = []
        for t in self._tasks.values():
            if view == "open" and t.done:
                continue
            if view == "done" and not t.done:
                continue
            if view == "today" and (t.done or not t.due or t.due.date() > today):
                continue  # due today or earlier (overdue included)
            if q and q not in t.title.lower() and not any(q in g.lower() for g in t.tags):
                continue
            out.append(t.copy())
        return sorted(out, key=_sort_key)

    def next_due(self, t: Task, now: datetime | None = None) -> datetime | None:
        """The next occurrence after the current one (or after now, if that is later). None if the repeat has ended."""
        if not (t.rrule and t.due):
            return None
        rule = compile_rule(t.rrule, t.series_start or t.due)
        return rule.after(max(t.due, now or D.now()), inc=False)

    # ---- writes ----------------------------------------------------------------------------
    def save(self, t: Task) -> Task:
        now = D.now()
        t.updated = now
        t.created = t.created or now
        if t.rrule and t.due and not t.series_start:
            t.series_start = t.due
        self._col.put(t.id, t.to_dict())
        self._tasks[t.id] = t.copy()
        self.api.emit("tasks.changed", task_id=t.id)
        return t

    def delete(self, task_id: str) -> None:
        self._col.delete(task_id)
        self._tasks.pop(task_id, None)
        self.api.emit("tasks.changed", task_id=task_id)

    def toggle(self, task_id: str) -> Task | None:
        """Tick off a task, or reopen it. A repeating task moves on to its next due date instead of finishing."""
        t = self.get(task_id)
        if t is None:
            return None
        now = D.now()
        if t.done:
            t.done, t.done_at = False, None
        elif t.rrule:
            nxt = self.next_due(t, now)
            t.last_done = now
            if nxt:
                t.due = nxt
            else:  # the repeat has run out
                t.done, t.done_at = True, now
        else:
            t.done, t.done_at, t.last_done = True, now, now
        return self.save(t)

    def add_task(self, title: str, due: datetime | None = None, has_time: bool = False, priority: int = 2,
                 tags=(), notes: str = "", rrule: str | None = None, reminders=()) -> str:
        if due is not None and not has_time:
            due = D.day_start(due)
        t = Task.new(title, due=due, has_time=bool(has_time and due), priority=priority, tags=list(tags),
                     notes=notes, rrule=rrule, reminders=sorted(set(reminders)))
        return self.save(t).id

    # ---- reminders -------------------------------------------------------------------------
    def due_reminders(self, since: datetime, until: datetime) -> list[Reminder]:
        """Reminders whose fire time falls in (since, until]. Only tasks with a due time can remind."""
        out = []
        for t in self._tasks.values():
            if t.done or not t.due or not t.has_time or not t.reminders:
                continue
            for m in t.reminders:
                at = t.due - timedelta(minutes=m)
                if since < at <= until:
                    detail = f"{t.due:%a %b} {t.due.day}, {D.fmt_time(t.due)}"
                    if t.priority == 1:
                        detail += " · high priority"
                    out.append(Reminder("tasks", t.title, at, t.due, detail,
                                        actions=(("Complete", "tasks.complete", (t.id,)),)))
        return sorted(out, key=lambda r: r.at)
