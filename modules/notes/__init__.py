"""Notes module scaffold"""
from __future__ import annotations

import contextlib
from datetime import datetime
from time import time
from ..base import Module

class NotesModule(Module):
    name = "notes"
    title = "Notes"
    show_in_navigation = True

    def setup(self):
        self.notes = self.col("notes")

    def services(self):
        return {
            "list_notes": self.list_notes,
            "add_note": self.add_note,
            "get_note": self.get_note,
            "update_note": self.update_note,
            "delete_note": self.delete_note,
        }

    def create_view(self, parent):
        from .ui import NotesView
        return NotesView(parent, self)

    def list_notes(self):
        notes = self.notes.all() or []
        # sort by date if present; safe fallback
        def _date(n):
            try:
                return datetime.fromisoformat(n.get("date"))
            except (ValueError, TypeError, AttributeError):
                return datetime.min
        with contextlib.suppress(Exception):
            notes.sort(key=_date, reverse=True)
        return notes

    def link_note_to_event(self, note_id: str, event_id: str) -> dict:
        rec = self.notes.get(note_id)
        if rec is None:
            raise ValueError(f"Unknown note: {note_id}")
        rec = dict(rec)
        rec["linked_event"] = event_id
        self.notes.put(note_id, rec)
        return rec

    def add_note(self, title: str, content: str, date: str | None = None, linked_event: str | None = None) -> dict:
        nid = f"note_{title.lower().replace(' ', '_')}"
        date_str = date if date is not None else datetime.now().date().isoformat()
        rec = {"id": nid, "title": title, "content": content, "date": date_str}
        if linked_event is not None:
            rec["linked_event"] = linked_event
        self.notes.put(nid, rec)
        return rec

    def get_note(self, note_id: str) -> dict | None:
        return self.notes.get(note_id)

    def update_note(self, note_id: str, title: str, content: str) -> dict:
        rec = self.notes.get(note_id)
        if rec is None:
            raise ValueError("Unknown note")
        rec = dict(rec)
        rec["title"] = title
        rec["content"] = content
        self.notes.put(note_id, rec)
        return rec

    def delete_note(self, note_id: str) -> bool:
        return self.notes.delete(note_id)
