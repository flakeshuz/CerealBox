"""Contacts module scaffold"""
from ..base import Module


class ContactsModule(Module):
    name = "contacts"
    title = "Contacts"

    def setup(self):
        self.people = self.col("contacts")

    def services(self):
        return {
            "list_contacts": self.list_contacts,
            "add_contact": self.add_contact,
            "update_last_contact": self.update_last_contact,
            "birthdays_entries": self.birthdays_entries,
        }

    def list_contacts(self):
        return self.people.all() or []

    def update_last_contact(self, contact_id: str) -> dict:
        rec = self.people.get(contact_id)
        if rec is None:
            raise ValueError(f"Unknown contact: {contact_id}")
        import datetime as _dt
        rec = dict(rec)
        rec["last_contact"] = _dt.datetime.now().isoformat()
        self.people.put(contact_id, rec)
        return rec

    def birthdays_entries(self) -> list[dict]:
        contacts = self.list_contacts() or []
        return [
            {"id": c.get("id"), "name": c.get("name"), "birthday": c.get("birthday")}
            for c in contacts if c.get("birthday")
        ]

    def add_contact(self, name: str, birthday: str | None = None) -> dict:
        cid = f"ct_{name.lower().replace(' ', '_')}"
        rec = {"id": cid, "name": name, "birthday": birthday}
        self.people.put(cid, rec)
        return rec
