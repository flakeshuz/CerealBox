"""Date/time helpers shared by every module.

Storage convention: datetimes are *naive local wall-clock time*, written as ISO-8601
("2026-11-16T09:00:00"). All-day items sit at midnight with an exclusive end, the same
way iCalendar does it. Anything that arrives with a timezone (e.g. .ics files) is
converted to local time at the boundary.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta

MONDAY, SUNDAY = 0, 6


# ---- basics -----------------------------------------------------------------------
def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def to_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def day_start(d: date | datetime) -> datetime:
    return datetime(d.year, d.month, d.day)


# ---- calendar maths -----------------------------------------------------------------
def week_start(d: date | datetime, first_weekday: int = SUNDAY) -> date:
    d = d.date() if isinstance(d, datetime) else d
    return d - timedelta(days=(d.weekday() - first_weekday) % 7)


def month_grid(year: int, month: int, first_weekday: int = SUNDAY) -> list[list[date]]:
    """Always six rows of seven dates, so the month view keeps a stable shape."""
    weeks = calendar.Calendar(first_weekday).monthdatescalendar(year, month)
    while len(weeks) < 6:
        nxt = weeks[-1][-1] + timedelta(days=1)
        weeks.append([nxt + timedelta(days=i) for i in range(7)])
    return weeks


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# ---- parsing (forgiving, for text boxes) --------------------------------------------
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y",
                 "%d %b %Y", "%d %B %Y", "%d/%m/%Y")
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?:\s*([ap])\.?m?\.?)?$", re.IGNORECASE)
_MIN_RE = re.compile(r"^(\d+)\s*(m|min|mins|minutes?|h|hr|hrs|hours?|d|days?|w|weeks?)?$", re.IGNORECASE)
_UNIT_MIN = {"m": 1, "h": 60, "d": 1440, "w": 10080}


def parse_date(text: str) -> date:
    text = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"I can't read the date '{text}'. Use a format like 2026-11-16 or 11/16/2026.")


def parse_time(text: str) -> time:
    m = _TIME_RE.match(text.strip())
    err = ValueError(f"I can't read the time '{text}'. Use a format like 9:30 AM or 14:00.")
    if not m:
        raise err
    h, mi, ap = int(m[1]), int(m[2] or 0), (m[3] or "").lower()
    if ap:
        if not 1 <= h <= 12:
            raise err
        h = h % 12 + (12 if ap == "p" else 0)
    if h > 23 or mi > 59:
        raise err
    return time(h, mi)


def parse_minutes(text: str) -> int:
    """'15' -> 15, '2h' -> 120, '1 day' -> 1440."""
    m = _MIN_RE.match(text.strip())
    if not m:
        raise ValueError(f"I can't read the reminder '{text}'. Try 15, 2h or 1d.")
    return int(m[1]) * _UNIT_MIN[(m[2] or "m")[0].lower()]


def parse_minute_list(text: str) -> list[int]:
    parts = [p for p in re.split(r"[;,]", text) if p.strip()]
    return sorted({parse_minutes(p) for p in parts})


# ---- formatting -----------------------------------------------------------------------
def fmt_time(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'AM' if dt.hour < 12 else 'PM'}"


def fmt_time_short(dt: datetime) -> str:
    h, suffix = dt.hour % 12 or 12, "a" if dt.hour < 12 else "p"
    return f"{h}{suffix}" if dt.minute == 0 else f"{h}:{dt.minute:02d}{suffix}"


def fmt_hour(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"


def fmt_date_long(d: date) -> str:
    return f"{d:%A, %B} {d.day}, {d.year}"


def fmt_minutes(n: int) -> str:
    if n == 0:
        return "at start"
    for size, unit in ((10080, "week"), (1440, "day"), (60, "hour"), (1, "minute")):
        if n % size == 0:
            q = n // size
            return f"{q} {unit}{'' if q == 1 else 's'}"
    return f"{n} minutes"


def fmt_span(minutes: int) -> str:
    """Compact human duration for 'in ...' / '... ago' text: 45 min, 2 h 15 min, 1 d 3 h."""
    minutes = abs(int(minutes))
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    if d:
        return f"{d} d" + (f" {h} h" if h else "")
    if h:
        return f"{h} h" + (f" {m} min" if m else "")
    return f"{m} min"


def compact_minutes(m: int) -> str:
    """15 -> '15m', 60 -> '1h', 1440 -> '1d' (the same shorthand the reminder boxes accept)."""
    if m and m % 1440 == 0:
        return f"{m // 1440}d"
    if m and m % 60 == 0:
        return f"{m // 60}h"
    return f"{m}m"
