"""Calendar module: events, categories, recurrence, reminders and .ics import/export.

This class is UI-free. The Tk screen (ui.py) and other modules both go through it.
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...core import dates as D
from ...core.api import Reminder
from ...core.ids import new_id
from ..base import Module
from . import ics
from .models import (
    DEFAULT_COLOR,
    IMPORT_PALETTE,
    Category,
    Event,
    Occurrence,
    default_categories,
)
from .recurrence import expand
from .subscriptions import Subscription, fetch_url


@dataclass
class ImportResult:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0  # events that disappeared from a calendar link
    categories: list[str] = field(default_factory=list)

    def summary(self) -> str:
        text = f"{self.added} new, {self.updated} updated"
        if self.removed:
            text += f", {self.removed} removed"
        if self.skipped:
            text += f", {self.skipped} skipped (cancelled or unreadable)"
        if self.categories:
            text += f".\nNew categories: {', '.join(self.categories)}"
        return text


class CalendarModule(Module):
    name = "calendar"
    title = "Calendar"

    # ---- lifecycle ---------------------------------------------------------------------
    def setup(self) -> None:
        self._ev_col, self._cat_col = self.col("events"), self.col("categories")
        self._sub_col = self.col("subscriptions")
        self.fetch = fetch_url  # replaceable, so tests can run without a network
        self._results: queue.Queue = queue.Queue()
        self._inflight: set[str] = set()
        self._load()
        if not self._cats:
            with self.api.vault.batch():
                for c in default_categories():
                    self._cat_col.put(c.id, c.to_dict())
            self._load()
        self.api.on("vault.reloaded", lambda **_: self._load())

    def _load(self) -> None:
        self._cats = {d["id"]: Category.from_dict(d) for d in self._cat_col.all()}
        self._events = {d["id"]: Event.from_dict(d) for d in self._ev_col.all()}
        self._subs = {d["id"]: Subscription.from_dict(d) for d in self._sub_col.all()}

    def services(self):
        """The calendar's public API for other modules. Plain data in, plain data out."""
        return {
            "add_event": self._svc_add_event,
            "events_between": self._svc_events_between,
            "reminders_due": self.due_reminders,
            "import_ics": self.import_ics,
            "export_ics": self.export_ics,
            "start_due_syncs": self.start_due_syncs,
            "subscriptions": self.subscriptions,
            "drain_syncs": self.drain_syncs,
        }

    def create_view(self, parent):
        from .ui import (
            CalendarView,  # imported lazily so the engine works without tkinter
        )

        return CalendarView(parent, self)

    # ---- categories --------------------------------------------------------------------
    def categories(self) -> list[Category]:
        return sorted(self._cats.values(), key=lambda c: c.name.lower())

    def category(self, cat_id: str | None) -> Category | None:
        return self._cats.get(cat_id) if cat_id else None

    def color_of(self, event: Event) -> str:
        cat = self.category(event.category_id)
        return cat.color if cat else DEFAULT_COLOR

    def save_category(self, cat: Category) -> None:
        self._cat_col.put(cat.id, cat.to_dict())
        self._cats[cat.id] = cat
        self.api.emit("calendar.categories.changed")

    def delete_category(self, cat_id: str) -> None:
        with self.api.vault.batch():
            self._cat_col.delete(cat_id)
            for ev in self._events.values():
                if ev.category_id == cat_id:
                    ev.category_id = None
                    self._ev_col.put(ev.id, ev.to_dict())
        self._cats.pop(cat_id, None)
        self.api.emit("calendar.categories.changed")

    # ---- events ------------------------------------------------------------------------
    def get_event(self, event_id: str) -> Event | None:
        ev = self._events.get(event_id)
        return ev.copy() if ev else None

    def _put_event(self, ev: Event) -> None:
        ev.updated = D.now()
        ev.created = ev.created or ev.updated
        self._ev_col.put(ev.id, ev.to_dict())
        self._events[ev.id] = ev.copy()

    def save_event(self, ev: Event) -> Event:
        self._check_editable(self._events.get(ev.id))
        self._put_event(ev)
        self.api.emit("calendar.event.saved", event_id=ev.id)
        return ev

    def delete_event(self, event_id: str) -> None:
        self._check_editable(self._events.get(event_id))
        self._ev_col.delete(event_id)
        self._events.pop(event_id, None)
        self.api.emit("calendar.event.deleted", event_id=event_id)

    def delete_occurrence(self, event_id: str, occ_start: datetime) -> None:
        """Remove just one showing of a recurring event."""
        self._check_editable(self._events.get(event_id))
        ev = self._events[event_id].copy()
        if not ev.rrule:
            return self.delete_event(event_id)
        if occ_start not in ev.exdates:
            ev.exdates.append(occ_start)
        self.save_event(ev)
        return None

    def detach_occurrence(self, event_id: str, occ_start: datetime, fields: dict) -> Event:
        """'Edit just this one': hide the occurrence in the series and save a standalone copy."""
        self._check_editable(self._events.get(event_id))
        master = self._events[event_id].copy()
        new = Event.new(fields["title"], fields["start"], fields["end"])
        for key in ("all_day", "category_id", "location", "notes", "reminders"):
            if key in fields:
                setattr(new, key, fields[key])
        with self.api.vault.batch():
            if occ_start not in master.exdates:
                master.exdates.append(occ_start)
            self._put_event(master)
            self._put_event(new)
        self.api.emit("calendar.event.saved", event_id=new.id)
        return new

    # ---- queries -----------------------------------------------------------------------
    def occurrences_between(self, start: datetime, end: datetime, hidden: set | None = None) -> list[Occurrence]:
        """Every occurrence overlapping [start, end). `hidden` = category ids (or None) to leave out."""
        hidden = hidden or set()
        out: list[Occurrence] = []
        for ev in self._events.values():
            if ev.category_id in hidden:
                continue
            out.extend(expand(ev, start, end))
        out.sort(key=lambda o: (o.start, not o.all_day, o.title.lower()))
        return out

    def upcoming(self, days: int = 14, limit: int = 100) -> list[Occurrence]:
        now = D.now()
        return self.occurrences_between(now, now + timedelta(days=days))[:limit]

    # ---- reminders ---------------------------------------------------------------------
    def due_reminders(self, since: datetime, until: datetime) -> list[Reminder]:
        """Reminders whose fire time falls in (since, until]."""
        out = []
        for ev in self._events.values():
            if not ev.reminders:
                continue
            lead = timedelta(minutes=max(ev.reminders))
            for occ in expand(ev, since, until + lead):
                for m in ev.reminders:
                    at = occ.start - timedelta(minutes=m)
                    if since < at <= until:
                        when = "all day" if ev.all_day else D.fmt_time(occ.start)
                        out.append(Reminder("calendar", occ.title, at, occ.start,
                                            f"{occ.start:%a %b} {occ.start.day}, {when}"
                                            + (f" - {ev.location}" if ev.location else "")))
        return sorted(out, key=lambda r: r.at)

    # ---- moving events -----------------------------------------------------------------------
    def _check_editable(self, ev: Event | None) -> None:
        if ev is not None and ev.source:
            sub = self._subs.get(ev.source)
            where = f" from “{sub.name}”" if sub else ""
            raise ValueError(f"This event{where} is read-only. It updates from its calendar link.")

    def move_occurrence(self, event_id: str, occ_start: datetime, new_start: datetime, scope: str = "this") -> Event:
        """Drag-to-move. scope 'this' detaches one showing of a repeat; 'all' shifts the whole series."""
        ev = self._events[event_id]
        self._check_editable(ev)
        duration = ev.end - ev.start
        delta = new_start - occ_start
        if ev.rrule and scope == "this":
            fields = {"title": ev.title, "start": new_start, "end": new_start + duration, "all_day": ev.all_day,
                      "category_id": ev.category_id, "location": ev.location, "notes": ev.notes,
                      "reminders": list(ev.reminders)}
            return self.detach_occurrence(event_id, occ_start, fields)
        moved = ev.copy()
        moved.start = ev.start + delta
        moved.end = moved.start + duration
        moved.exdates = [x + delta for x in ev.exdates]
        return self.save_event(moved)

    # ---- calendar links (.ics subscriptions) ------------------------------------------------------
    def subscriptions(self) -> list[Subscription]:
        return sorted((s.copy() for s in self._subs.values()), key=lambda s: s.name.lower())

    def save_subscription(self, sub: Subscription) -> None:
        self._sub_col.put(sub.id, sub.to_dict())
        self._subs[sub.id] = sub.copy()
        self.api.emit("calendar.subscriptions.changed")

    def remove_subscription(self, sub_id: str) -> None:
        with self.api.vault.batch():
            for ev in [e for e in self._events.values() if e.source == sub_id]:
                self._ev_col.delete(ev.id)
                self._events.pop(ev.id, None)
            self._sub_col.delete(sub_id)
            self._subs.pop(sub_id, None)
        self._inflight.discard(sub_id)
        self.api.emit("calendar.subscriptions.changed")
        self.api.emit("calendar.synced", source=sub_id)

    def start_sync(self, sub_id: str, now: datetime | None = None) -> bool:
        """Fetch a link in the background. Returns False if it's missing or already being fetched."""
        sub = self._subs.get(sub_id)
        if sub is None or sub_id in self._inflight:
            return False
        self._inflight.add(sub_id)
        marked = sub.copy()
        marked.last_attempt = now or D.now()
        self.save_subscription(marked)
        url, fetch = sub.url, self.fetch

        def work() -> None:
            try:
                self._results.put((sub_id, fetch(url), None))
            except Exception as exc:  # network errors, bad links, non-calendar pages
                logging.getLogger(__name__).exception("Calendar fetch failed: %s", sub_id)
                self._results.put((sub_id, None, str(exc) or exc.__class__.__name__))

        threading.Thread(target=work, daemon=True).start()
        return True

    def start_due_syncs(self, now: datetime | None = None) -> int:
        now = now or D.now()
        started = 0
        for sub in list(self._subs.values()):
            due = sub.last_attempt is None or now - sub.last_attempt >= timedelta(minutes=sub.interval_min)
            if sub.enabled and due and self.start_sync(sub.id, now):
                started += 1
        return started

    def drain_syncs(self) -> list[str]:
        """Apply finished fetches. Runs on the main thread only. Returns the ids that were processed."""
        done = []
        while True:
            try:
                sub_id, text, err = self._results.get_nowait()
            except queue.Empty:
                break
            self._inflight.discard(sub_id)
            if sub_id not in self._subs:
                continue
            if err is None:
                try:
                    self.apply_sync(sub_id, text)
                    done.append(sub_id)
                    continue
                except Exception as exc:  # a feed we can fetch but can't read
                    logging.getLogger(__name__).exception("Calendar sync failed: %s", sub_id)
                    err = f"Couldn't read the calendar: {exc}"
            failed = self._subs[sub_id].copy()
            failed.last_error = err
            self.save_subscription(failed)
            done.append(sub_id)
        return done

    def _resolve_category(self, name: str | None, res: ImportResult) -> str | None:
        if not name:
            return None
        cat = next((c for c in self._cats.values() if c.name.lower() == name.lower()), None)
        if cat is None:
            cat = Category(new_id("cat"), name, IMPORT_PALETTE[len(self._cats) % len(IMPORT_PALETTE)])
            self._cat_col.put(cat.id, cat.to_dict())
            self._cats[cat.id] = cat
            res.categories.append(name)
        return cat.id

    def apply_sync(self, sub_id: str, text: str) -> ImportResult:
        """Make the link's events match the feed: add new, update changed, remove gone."""
        sub = self._subs[sub_id]
        parsed, skipped = ics.parse_events(text)
        res = ImportResult(skipped=skipped)
        existing = {e.uid: e for e in self._events.values() if e.source == sub_id}
        seen: set[str] = set()
        masters: dict[str, Event] = {}
        with self.api.vault.batch():
            for p in parsed:
                if p.recurrence_id is not None:
                    continue
                ev = p.event
                ev.source = sub_id
                ev.category_id = self._resolve_category(p.category_name, res)
                old = existing.get(ev.uid)
                if old:
                    ev.id, ev.created = old.id, old.created
                    res.updated += 1
                else:
                    res.added += 1
                self._put_event(ev)
                masters[ev.uid] = ev
                seen.add(ev.uid)
            for p in parsed:  # single occurrences edited or cancelled in the source calendar
                if p.recurrence_id is None:
                    continue
                master = masters.get(p.event.uid)
                if master and p.recurrence_id not in master.exdates:
                    master.exdates.append(p.recurrence_id)
                    self._put_event(master)
                if p.cancelled:
                    continue
                ev = p.event
                key = f"{ev.uid}#{D.to_iso(p.recurrence_id)}"
                ev.uid, ev.rrule, ev.source = key, None, sub_id
                ev.category_id = self._resolve_category(p.category_name, res) or (master.category_id if master else None)
                old = existing.get(key)
                if old:
                    ev.id, ev.created = old.id, old.created
                    res.updated += 1
                else:
                    res.added += 1
                self._put_event(ev)
                seen.add(key)
            for uid, old in existing.items():
                if uid not in seen:
                    self._ev_col.delete(old.id)
                    self._events.pop(old.id, None)
                    res.removed += 1
            synced = sub.copy()
            synced.last_sync, synced.last_error = D.now(), ""
            self.save_subscription(synced)
        self.api.emit("calendar.synced", source=sub_id, result=res)
        return res

    # ---- .ics ----------------------------------------------------------------------------
    def import_ics(self, text: str) -> ImportResult:
        parsed, skipped = ics.parse_events(text)
        res = ImportResult(skipped=skipped)
        by_uid = {e.uid: e for e in self._events.values() if e.uid and not e.source}
        by_name = {c.name.lower(): c for c in self._cats.values()}

        def resolve(name: str | None) -> str | None:
            if not name:
                return None
            cat = by_name.get(name.lower())
            if cat is None:
                cat = Category(new_id("cat"), name, IMPORT_PALETTE[len(self._cats) % len(IMPORT_PALETTE)])
                self._cat_col.put(cat.id, cat.to_dict())
                self._cats[cat.id] = cat
                by_name[name.lower()] = cat
                res.categories.append(name)
            return cat.id

        def store(ev: Event) -> None:
            old = by_uid.get(ev.uid)
            if old:  # same UID seen before: update in place, keep our id and any category we set
                ev.id, ev.created = old.id, old.created
                ev.category_id = ev.category_id or old.category_id
                res.updated += 1
            else:
                res.added += 1
            self._put_event(ev)
            by_uid[ev.uid] = ev

        with self.api.vault.batch():
            for p in (p for p in parsed if p.recurrence_id is None):
                p.event.category_id = resolve(p.category_name)
                store(p.event)
            for p in (p for p in parsed if p.recurrence_id is not None):  # edited/cancelled single instances
                master = by_uid.get(p.event.uid)
                if master and p.recurrence_id not in master.exdates:
                    master.exdates.append(p.recurrence_id)
                    self._put_event(master)
                if p.cancelled:
                    continue
                ev = p.event
                ev.uid, ev.rrule = f"{ev.uid}#{D.to_iso(p.recurrence_id)}", None
                ev.category_id = resolve(p.category_name) or (master.category_id if master else None)
                store(ev)
        self.api.emit("calendar.imported", result=res)
        return res

    def export_ics(self, event_ids: list[str] | None = None) -> str:
        events = [e for e in self._events.values() if event_ids is None or e.id in event_ids]
        events.sort(key=lambda e: e.start)
        return ics.events_to_ics(events, {c.id: c.name for c in self._cats.values()})

    # ---- services for other modules -----------------------------------------------------
    def _svc_add_event(self, title: str, start: datetime, end: datetime | None = None, *, all_day: bool = False,
                       category: str | None = None, reminders=(), notes: str = "", location: str = "") -> str:
        """e.g. the future Taxes module: api.call('calendar.add_event', 'Q4 estimated tax due', date, all_day=True)."""
        cat = next((c for c in self._cats.values() if category and c.name.lower() == category.lower()), None)
        if all_day:
            start = D.day_start(start)
            end = D.day_start(end) if end else start + timedelta(days=1)
        ev = Event.new(title, start, end, all_day=all_day, category_id=cat.id if cat else None,
                       reminders=list(reminders), notes=notes, location=location)
        return self.save_event(ev).id

    def _svc_events_between(self, start: datetime, end: datetime) -> list[dict]:
        return [{"id": o.event.id, "title": o.title, "start": o.start, "end": o.end, "all_day": o.all_day,
                 "category": (self.category(o.event.category_id) or Category("", "", "")).name or None}
                for o in self.occurrences_between(start, end)]
