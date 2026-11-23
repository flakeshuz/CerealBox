"""RFC 5545 recurrence rules, shared by every module (calendar, tasks, ...).

Rules are stored as plain RRULE strings, e.g. "FREQ=WEEKLY;BYDAY=MO,WE". This module understands
the subset the editors produce and parses anything else on a best-effort basis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache

from dateutil.rrule import rrule, rrulestr

WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
REPEAT_NONE = "Does not repeat"
REPEAT_CUSTOM = "Custom (kept as is)"  # a rule the editor can't express, e.g. imported from another app
REPEAT_CHOICES = [REPEAT_NONE, "Daily", "Weekly", "Monthly", "Yearly"]
FREQ_BY_LABEL = {"Daily": "DAILY", "Weekly": "WEEKLY", "Monthly": "MONTHLY", "Yearly": "YEARLY"}
LABEL_BY_FREQ = {v: k for k, v in FREQ_BY_LABEL.items()}

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_SIMPLE_KEYS = {"FREQ", "INTERVAL", "BYDAY", "COUNT", "UNTIL", "WKST"}


# ---- normalising rules that came from other apps ----------------------------------------
def normalize_rrule(rule: str) -> str:
    """Strip 'RRULE:' and convert UNTIL to local wall-clock time, matching our naive datetimes."""
    rule = rule.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[6:]
    parts = []
    for part in filter(None, rule.split(";")):
        key, _, val = part.partition("=")
        key = key.upper()
        if key == "UNTIL":
            val = _until_to_local(val)
        parts.append(f"{key}={val}")
    return ";".join(parts)


def _until_to_local(v: str) -> str:
    if len(v) == 8:  # date only -> include the whole last day
        return v + "T235959"
    if v.upper().endswith("Z"):
        dt = datetime.strptime(v[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().replace(tzinfo=None).strftime("%Y%m%dT%H%M%S")
    return v


@lru_cache(maxsize=256)
def compile_rule(rule: str, dtstart: datetime) -> rrule:
    return rrulestr(normalize_rrule(rule), dtstart=dtstart, cache=True)


# ---- building / parsing the simple rules the editor understands -----------------------------
def build_rrule(freq: str, interval: int = 1, byday: list[str] | None = None,
                count: int | None = None, until: date | None = None) -> str:
    parts = [f"FREQ={freq.upper()}"]
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    if freq.upper() == "WEEKLY" and byday:
        parts.append("BYDAY=" + ",".join(byday))
    if count:
        parts.append(f"COUNT={count}")
    elif until:
        parts.append("UNTIL=" + until.strftime("%Y%m%d") + "T235959")
    return ";".join(parts)


@dataclass
class RuleParts:
    freq: str = ""
    interval: int = 1
    byday: list[str] = field(default_factory=list)
    count: int | None = None
    until: date | None = None
    custom: bool = False  # True if the rule uses features the editor can't represent


def parse_rrule(rule: str) -> RuleParts:
    p = RuleParts()
    try:
        for part in normalize_rrule(rule).split(";"):
            key, _, val = part.partition("=")
            if key == "FREQ":
                p.freq = val
            elif key == "INTERVAL":
                p.interval = max(1, int(val))
            elif key == "BYDAY":
                p.byday = val.split(",")
            elif key == "COUNT":
                p.count = int(val)
            elif key == "UNTIL":
                p.until = datetime.strptime(val[:8], "%Y%m%d").date()
            elif key not in _SIMPLE_KEYS:
                p.custom = True
    except ValueError:
        p.custom = True
    if p.freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        p.custom = True
    if p.byday and (p.freq != "WEEKLY" or any(c not in WEEKDAY_CODES for c in p.byday)):
        p.custom = True  # e.g. "1MO" (first Monday) or BYDAY on a monthly rule
    return p


def describe_rrule(rule: str) -> str:
    p = parse_rrule(rule)
    unit = {"DAILY": "day", "WEEKLY": "week", "MONTHLY": "month", "YEARLY": "year"}.get(p.freq)
    if not unit:
        return "Repeats (custom rule)"
    text = f"Every {unit}" if p.interval == 1 else f"Every {p.interval} {unit}s"
    if p.byday and not p.custom:
        text += " on " + ", ".join(WEEKDAY_NAMES[WEEKDAY_CODES.index(c)] for c in p.byday)
    if p.count:
        text += f", {p.count} times"
    elif p.until:
        text += f", until {p.until:%b} {p.until.day}, {p.until.year}"
    return text + (" (custom rule)" if p.custom else "")
