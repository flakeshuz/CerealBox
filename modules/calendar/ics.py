"""iCalendar (.ics) import and export - the subset real calendars actually use.

Import understands: DTSTART/DTEND/DURATION (date, floating, UTC "Z" and TZID forms),
SUMMARY/DESCRIPTION/LOCATION, RRULE, EXDATE, CATEGORIES, VALARM triggers, and
RECURRENCE-ID overrides (the "edited just this one" instances Google/Apple export).
Times with a timezone are converted to local wall-clock time.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...core import dates as D
from ...core.ids import new_id
from .models import Event
from .recurrence import normalize_rrule

WINDOWS_TZ = {
    "Pacific Standard Time": "America/Los_Angeles", "Mountain Standard Time": "America/Denver",
    "Central Standard Time": "America/Chicago", "Eastern Standard Time": "America/New_York",
    "Alaskan Standard Time": "America/Anchorage", "Hawaiian Standard Time": "Pacific/Honolulu",
    "GMT Standard Time": "Europe/London", "W. Europe Standard Time": "Europe/Berlin", "UTC": "UTC",
}
_DUR_RE = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


@dataclass
class ParsedEvent:
    event: Event
    category_name: str | None = None
    recurrence_id: datetime | None = None  # set => this VEVENT overrides one occurrence
    cancelled: bool = False


# =============================== parsing ======================================================
def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split_outside_quotes(s: str, sep: str) -> list[str]:
    parts, cur, quoted = [], [], False
    for ch in s:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _split_line(line: str):
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            head, value = line[:i], line[i + 1 :]
            parts = _split_outside_quotes(head, ";")
            params = {}
            for p in parts[1:]:
                k, _, v = p.partition("=")
                params[k.upper()] = v.strip('"')
            return parts[0].upper(), params, value
    return None


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append("\n" if s[i + 1] in "nN" else s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _parse_dt(value: str, params: dict) -> tuple[datetime, bool]:
    """-> (naive local datetime, is_date_only)"""
    value = value.strip()
    if params.get("VALUE") == "DATE" or len(value) == 8:
        return datetime.strptime(value[:8], "%Y%m%d"), True
    if value.endswith(("Z", "z")):
        dt = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().replace(tzinfo=None), False
    dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
    tzid = params.get("TZID")
    if tzid:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(WINDOWS_TZ.get(tzid, tzid))).astimezone().replace(tzinfo=None)
        except (ZoneInfoNotFoundError, ValueError):
            logging.getLogger(__name__).warning("Unknown timezone %r; treating event as local time", tzid)
    return dt, False


def _parse_duration(value: str) -> timedelta | None:
    m = _DUR_RE.match(value.strip())
    if not m:
        return None
    w, d, h, mi, s = (int(x or 0) for x in m.groups()[1:])
    td = timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)
    return -td if m[1] == "-" else td


def _components(lines: list[str]) -> list[dict]:
    """Collect each VEVENT as {'props': [(name, params, value)], 'alarms': [[props]]}."""
    events, stack, cur, alarm = [], [], None, None
    for line in lines:
        parsed = _split_line(line)
        if not parsed:
            continue
        name, _params, value = parsed
        if name == "BEGIN":
            stack.append(value.upper())
            if stack[-1] == "VEVENT":
                cur = {"props": [], "alarms": []}
            elif stack[-1] == "VALARM" and cur is not None:
                alarm = []
        elif name == "END":
            top = stack.pop() if stack else None
            if top == "VEVENT" and cur is not None:
                events.append(cur)
                cur = None
            elif top == "VALARM" and cur is not None and alarm is not None:
                cur["alarms"].append(alarm)
                alarm = None
        elif stack and cur is not None:
            if stack[-1] == "VEVENT":
                cur["props"].append(parsed)
            elif stack[-1] == "VALARM" and alarm is not None:
                alarm.append(parsed)
    return events


def _to_event(comp: dict) -> ParsedEvent | None:
    props: dict = {}
    exdates: list = []
    cats: list = []
    for name, params, value in comp["props"]:
        if name == "EXDATE":
            exdates.append((params, value))
        elif name == "CATEGORIES":
            cats.append(value)
        else:
            props.setdefault(name, (params, value))
    if "DTSTART" not in props:
        return None
    start, all_day = _parse_dt(props["DTSTART"][1], props["DTSTART"][0])
    if "DTEND" in props:
        end, _ = _parse_dt(props["DTEND"][1], props["DTEND"][0])
    elif "DURATION" in props and (td := _parse_duration(props["DURATION"][1])) is not None:
        end = start + td
    else:
        end = start + timedelta(days=1) if all_day else start
    if end < start or (all_day and end == start):
        end = start + (timedelta(days=1) if all_day else timedelta(0))

    title = _unescape(props.get("SUMMARY", ({}, ""))[1])
    uid = props.get("UID", ({}, ""))[1].strip()
    if not uid:  # stable fallback so re-importing the same file doesn't duplicate
        uid = hashlib.sha1(f"{title}|{D.to_iso(start)}".encode()).hexdigest() + "@imported"

    ex = []
    for params, value in exdates:
        for v in value.split(","):
            if v.strip():
                d, date_only = _parse_dt(v, params)
                ex.append(datetime.combine(d.date(), start.time()) if date_only and not all_day else d)

    reminders = set()
    for alarm in comp["alarms"]:
        for name, params, value in alarm:
            if name == "TRIGGER" and params.get("VALUE", "DURATION") == "DURATION" and params.get("RELATED") != "END":
                td = _parse_duration(value)
                if td is not None and td <= timedelta(0):
                    reminders.add(int(-td.total_seconds() // 60))

    category = None
    for raw in cats:
        first = next((_unescape(c).strip() for c in _split_outside_quotes(raw, ",") if c.strip()), None)
        if first:
            category = first
            break

    rrule = normalize_rrule(props["RRULE"][1]) if "RRULE" in props else None
    rec_id = _parse_dt(props["RECURRENCE-ID"][1], props["RECURRENCE-ID"][0])[0] if "RECURRENCE-ID" in props else None
    event = Event(
        id=new_id("evt"), title=title, start=start, end=end, all_day=all_day,
        location=_unescape(props.get("LOCATION", ({}, ""))[1]),
        notes=_unescape(props.get("DESCRIPTION", ({}, ""))[1]),
        rrule=rrule, exdates=sorted(set(ex)), reminders=sorted(reminders), uid=uid,
    )
    cancelled = props.get("STATUS", ({}, ""))[1].strip().upper() == "CANCELLED"
    return ParsedEvent(event, category, rec_id, cancelled)


def parse_events(text: str) -> tuple[list[ParsedEvent], int]:
    """-> (parsed events, number of VEVENTs skipped as unusable)."""
    out, skipped = [], 0
    for comp in _components(_unfold(text)):
        try:
            pe = _to_event(comp)
        except (ValueError, KeyError):
            pe = None
        if pe is None or (pe.cancelled and pe.recurrence_id is None):
            skipped += 1
        else:
            out.append(pe)
    return out, skipped


# =============================== export =======================================================
def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, cur, n = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if n + b > 75:
            out.append(cur)
            cur, n = " " + ch, 1 + b
        else:
            cur, n = cur + ch, n + b
    out.append(cur)
    return "\r\n".join(out)


def _trigger(minutes: int) -> str:
    if minutes == 0:
        return "PT0S"
    d, rem = divmod(minutes, 1440)
    h, mi = divmod(rem, 60)
    return "-P" + (f"{d}D" if d else "") + ("T" if h or mi else "") + (f"{h}H" if h else "") + (f"{mi}M" if mi else "")


def events_to_ics(events: list[Event], category_names: dict[str, str] | None = None) -> str:
    """Times are written as floating local time (no timezone), which every app reads as 'local'."""
    category_names = category_names or {}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//CerealBox//Calendar//EN", "CALSCALE:GREGORIAN"]
    for ev in events:
        fmt, key = ("%Y%m%d", ";VALUE=DATE") if ev.all_day else ("%Y%m%dT%H%M%S", "")
        lines += ["BEGIN:VEVENT", f"UID:{ev.uid or ev.id}", f"DTSTAMP:{stamp}",
                  f"DTSTART{key}:{ev.start.strftime(fmt)}", f"DTEND{key}:{ev.end.strftime(fmt)}",
                  f"SUMMARY:{_escape(ev.title)}"]
        if ev.location:
            lines.append(f"LOCATION:{_escape(ev.location)}")
        if ev.notes:
            lines.append(f"DESCRIPTION:{_escape(ev.notes)}")
        if ev.category_id in category_names:
            lines.append(f"CATEGORIES:{_escape(category_names[ev.category_id])}")
        if ev.rrule:
            rule = normalize_rrule(ev.rrule)
            if ev.all_day:  # UNTIL must be a DATE for all-day events
                rule = re.sub(r"UNTIL=(\d{8})T\d{6}Z?", r"UNTIL=\1", rule)
            lines.append(f"RRULE:{rule}")
        for ex in ev.exdates:
            lines.append(f"EXDATE{key}:{ex.strftime(fmt)}")
        for m in ev.reminders:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(ev.title)}",
                      f"TRIGGER:{_trigger(m)}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
