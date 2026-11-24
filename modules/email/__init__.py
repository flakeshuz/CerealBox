"""Email module scaffold"""
from __future__ import annotations

from datetime import datetime
from ...core.ids import new_id
from ..base import Module


class EmailModule(Module):
    name = "email"
    title = "Email"

    def setup(self):
        self.inbox = self.col("emails.inbox")
        self.archived = self.col("emails.archived")

    def services(self):
        return {
            "list_inbox": self.list_inbox,
            "list_archived": self.list_archived,
            "receive_email": self.receive_email,
            "mark_read": self.mark_read,
            "archive": self.archive,
            "get_email": self.get_email,
        }

    def list_inbox(self):
        return self.inbox.all()

    def list_archived(self):
        return self.archived.all()

    def receive_email(self, from_addr: str, to_addr: str, subject: str, body: str, date: str | None = None) -> dict:
        eid = new_id("eml")
        date_str = date or __import__('datetime').datetime.now().isoformat()
        rec = {
            "id": eid,
            "from": from_addr,
            "to": to_addr,
            "subject": subject,
            "body": body,
            "date": date_str,
            "read": False,
            "archived": False,
        }
        self.inbox.put(eid, rec)
        return rec

    def mark_read(self, email_id: str) -> dict | None:
        rec = self.inbox.get(email_id)
        if rec is None:
            return None
        rec = dict(rec)
        rec["read"] = True
        self.inbox.put(email_id, rec)
        return rec

    def archive(self, email_id: str) -> dict | None:
        rec = self.inbox.get(email_id)
        if rec is None:
            return None
        arch = dict(rec)
        arch["archived"] = True
        self.archived.put(email_id, arch)
        self.inbox.delete(email_id)
        return arch

    def get_email(self, email_id: str) -> dict | None:
        rec = self.inbox.get(email_id)
        if rec is not None:
            return rec
        return self.archived.get(email_id)
