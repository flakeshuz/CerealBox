"""Calendar links: fetch an .ics address (Google, Apple, Outlook) and keep its events up to date.

Only the network fetch happens off the main thread. Parsing and saving always happen on the
main thread, because the vault is not thread-safe.
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime

from ...core import dates as D
from ...core.ids import new_id

MAX_BYTES = 10 * 1024 * 1024
DEFAULT_INTERVAL_MIN = 60


@dataclass
class Subscription:
    id: str
    name: str
    url: str  # treat as a secret: anyone with this link can read the calendar
    interval_min: int = DEFAULT_INTERVAL_MIN
    enabled: bool = True
    last_attempt: datetime | None = None
    last_sync: datetime | None = None
    last_error: str = ""

    @classmethod
    def new(cls, name: str, url: str, interval_min: int = DEFAULT_INTERVAL_MIN) -> Subscription:
        return cls(new_id("sub"), name, url, interval_min)

    def copy(self) -> Subscription:
        return replace(self)

    def to_dict(self) -> dict:
        iso = lambda v: D.to_iso(v) if v else None
        return {"id": self.id, "name": self.name, "url": self.url, "interval_min": self.interval_min,
                "enabled": self.enabled, "last_attempt": iso(self.last_attempt), "last_sync": iso(self.last_sync),
                "last_error": self.last_error}

    @classmethod
    def from_dict(cls, d: dict) -> Subscription:
        p = lambda v: D.from_iso(v) if v else None
        return cls(d["id"], d["name"], d["url"], int(d.get("interval_min", DEFAULT_INTERVAL_MIN)),
                   bool(d.get("enabled", True)), p(d.get("last_attempt")), p(d.get("last_sync")),
                   d.get("last_error", ""))


def normalize_url(url: str) -> str:
    u = url.strip()
    if u.lower().startswith("webcal://"):
        u = "https://" + u[len("webcal://"):]
    if not u.lower().startswith(("https://", "http://")):
        raise ValueError("The link should start with https:// (or webcal://).")
    return u


def fetch_url(url: str, timeout: float = 20.0) -> str:
    req = urllib.request.Request(normalize_url(url), headers={"User-Agent": "LifeOS/0.1 (calendar link)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("That calendar is larger than 10 MB.")
    text = data.decode("utf-8-sig", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("That link didn't return a calendar (.ics) file.")
    return text
