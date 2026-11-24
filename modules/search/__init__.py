# Search module scaffold
from ..base import Module


class SearchModule(Module):
    name = "search"
    title = "Search"

    def setup(self):
        pass

    def services(self):
        return {"global_search": self.global_search}

    def global_search(self, term: str) -> list:
        # Lightweight global search across notes, contacts, and calendar (best-effort)
        term_l = (term or "").lower()
        results = []
        if not term_l:
            return results
        try:
            notes = self.api.call("notes.list_notes") or []
            for n in notes:
                if term_l in (n.get("title", "") + " " + n.get("content", "")).lower():
                    results.append({"module": "notes", "record": n})
        except Exception:
            pass
        try:
            contacts = self.api.call("contacts.list_contacts") or []
            for c in contacts:
                if term_l in str(c.get("name", "")).lower() or term_l in str(c.get("birthday", "")).lower():
                    results.append({"module": "contacts", "record": c})
        except Exception:
            pass
        # calendar events for a broad time window
        from datetime import datetime, timedelta
        try:
            now = datetime.now()
            end = now + timedelta(days=365)
            events = self.api.call("calendar.events_between", now, end) or []
            for e in events:
                if term_l in str(e.get("title", "")).lower():
                    results.append({"module": "calendar", "record": e})
        except Exception:
            pass
        return results
