"""Calendar data models. Plain dataclasses that round-trip to JSON-friendly dicts."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from ...core import dates as D
from ...core.ids import new_id

DEFAULT_COLOR = "#6B7280"  # used when an event has no category

DEFAULT_CATEGORIES = [  # colours chosen so the label on each one reads at 4.5:1 or better
    ("personal", "Personal", "#2F6FD6"),
    ("work", "Work", "#6A4BD1"),
    ("family", "Family", "#B0550F"),
    ("health", "Health", "#17805A"),
    ("finance", "Finance", "#8C6500"),
    ("taxes", "Taxes", "#C8323F"),
    ("travel", "Travel", "#0B7F8E"),
    ("birthdays", "Birthdays", "#C2437F"),
]
IMPORT_PALETTE = ["#2F6FD6", "#6A4BD1", "#B0550F", "#17805A", "#0B7F8E", "#C2437F", "#8C6500", "#C8323F"]


@dataclass
class Category:
    id: str
    name: str
    color: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "color": self.color}

    @classmethod
    def from_dict(cls, d: dict) -> Category:
        return cls(id=d["id"], name=d["name"], color=d.get("color", DEFAULT_COLOR))


def default_categories() -> list[Category]:
    return [Category(f"cat_{slug}", name, color) for slug, name, color in DEFAULT_CATEGORIES]


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool = False  # all-day: start/end at midnight, end exclusive
    category_id: str | None = None
    location: str = ""
    notes: str = ""
    rrule: str | None = None  # RFC 5545 RRULE body, e.g. "FREQ=WEEKLY;BYDAY=MO,WE"
    exdates: list[datetime] = field(default_factory=list)  # occurrence starts to skip
    reminders: list[int] = field(default_factory=list)  # minutes before start
    uid: str = ""  # iCalendar UID, used to de-duplicate imports
    created: datetime | None = None
    updated: datetime | None = None
    source: str | None = None  # id of the calendar link this event came from; such events are read-only

    @classmethod
    def new(cls, title: str, start: datetime, end: datetime | None = None, **kw) -> Event:
        eid = new_id("evt")
        if end is None:
            end = start + (timedelta(days=1) if kw.get("all_day") else timedelta(hours=1))
        kw.setdefault("uid", f"{eid}@cerealbox.local")
        return cls(id=eid, title=title, start=start, end=end, **kw)

    @property
    def is_recurring(self) -> bool:
        return bool(self.rrule)

    def copy(self) -> Event:
        return replace(self, exdates=list(self.exdates), reminders=list(self.reminders))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start": D.to_iso(self.start),
            "end": D.to_iso(self.end),
            "all_day": self.all_day,
            "category_id": self.category_id,
            "location": self.location,
            "notes": self.notes,
            "rrule": self.rrule,
            "exdates": [D.to_iso(x) for x in self.exdates],
            "reminders": list(self.reminders),
            "uid": self.uid,
            "created": D.to_iso(self.created) if self.created else None,
            "updated": D.to_iso(self.updated) if self.updated else None,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        return cls(
            id=d["id"],
            title=d.get("title", ""),
            start=D.from_iso(d["start"]),
            end=D.from_iso(d["end"]),
            all_day=bool(d.get("all_day")),
            category_id=d.get("category_id"),
            location=d.get("location", ""),
            notes=d.get("notes", ""),
            rrule=d.get("rrule") or None,
            exdates=[D.from_iso(x) for x in d.get("exdates", [])],
            reminders=[int(m) for m in d.get("reminders", [])],
            uid=d.get("uid", ""),
            created=D.from_iso(d["created"]) if d.get("created") else None,
            updated=D.from_iso(d["updated"]) if d.get("updated") else None,
            source=d.get("source"),
        )


@dataclass(frozen=True, eq=False)
class Occurrence:
    """One concrete showing of an event (a recurring event has many)."""

    event: Event
    start: datetime
    end: datetime

    @property
    def all_day(self) -> bool:
        return self.event.all_day

    @property
    def title(self) -> str:
        return self.event.title or "(No title)"

    def days(self) -> list[date]:
        """Every calendar date this occurrence touches (end is exclusive)."""
        last = (self.end - timedelta(seconds=1)).date() if self.end > self.start else self.start.date()
        n = (last - self.start.date()).days
        return [self.start.date() + timedelta(days=i) for i in range(n + 1)]
