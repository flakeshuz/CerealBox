"""Task data model. A task is a to-do with an optional due date, priority, tags, repeat and reminders."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from ...core import dates as D
from ...core.ids import new_id

PRIORITY_NAMES = {1: "High", 2: "Normal", 3: "Low"}
PRIORITY_CODES = {v: k for k, v in PRIORITY_NAMES.items()}


def _iso(v: datetime | None) -> str | None:
    return D.to_iso(v) if v else None


def _parse(v: str | None) -> datetime | None:
    return D.from_iso(v) if v else None


@dataclass
class Task:
    id: str
    title: str
    due: datetime | None = None  # midnight when has_time is False
    has_time: bool = False
    priority: int = 2  # 1 high, 2 normal, 3 low
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    rrule: str | None = None  # repeat rule; `due` is the current occurrence
    series_start: datetime | None = None  # first occurrence, the anchor the repeat rule counts from
    reminders: list[int] = field(default_factory=list)  # minutes before `due`
    done: bool = False
    done_at: datetime | None = None
    last_done: datetime | None = None  # last time a repeating task was ticked off
    created: datetime | None = None
    updated: datetime | None = None

    @classmethod
    def new(cls, title: str, **kw) -> Task:
        return cls(id=new_id("tsk"), title=title, **kw)

    def copy(self) -> Task:
        return replace(self, tags=list(self.tags), reminders=list(self.reminders))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "due": _iso(self.due), "has_time": self.has_time,
            "priority": self.priority, "tags": list(self.tags), "notes": self.notes, "rrule": self.rrule,
            "series_start": _iso(self.series_start), "reminders": list(self.reminders), "done": self.done,
            "done_at": _iso(self.done_at), "last_done": _iso(self.last_done),
            "created": _iso(self.created), "updated": _iso(self.updated),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        return cls(
            id=d["id"], title=d.get("title", ""), due=_parse(d.get("due")), has_time=bool(d.get("has_time")),
            priority=int(d.get("priority", 2)), tags=list(d.get("tags", [])), notes=d.get("notes", ""),
            rrule=d.get("rrule") or None, series_start=_parse(d.get("series_start")),
            reminders=[int(m) for m in d.get("reminders", [])], done=bool(d.get("done")),
            done_at=_parse(d.get("done_at")), last_done=_parse(d.get("last_done")),
            created=_parse(d.get("created")), updated=_parse(d.get("updated")),
        )
