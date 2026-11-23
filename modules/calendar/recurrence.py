"""Calendar recurrence: expand a stored rule into the occurrences visible in a date range."""
from __future__ import annotations

from datetime import datetime, timedelta

from ...core.rrule import (
    WEEKDAY_CODES,
    WEEKDAY_NAMES,
    RuleParts,
    build_rrule,
    compile_rule,
    describe_rrule,
    normalize_rrule,
    parse_rrule,
)
from .models import Event, Occurrence

__all__ = ["WEEKDAY_CODES", "WEEKDAY_NAMES", "RuleParts", "build_rrule", "describe_rrule", "expand",
           "normalize_rrule", "parse_rrule"]


# ---- expansion ------------------------------------------------------------------------------
def _hits(s: datetime, e: datetime, rs: datetime, re: datetime) -> bool:
    """Does [s, e) overlap [rs, re)? Zero-length items count if they start inside."""
    return s < re and (e > rs or (e == s and s >= rs))


def expand(event: Event, range_start: datetime, range_end: datetime) -> list[Occurrence]:
    """All occurrences of `event` that overlap [range_start, range_end)."""
    dur = max(event.end - event.start, timedelta(0))
    rule = None
    if event.rrule:
        try:
            rule = compile_rule(event.rrule, event.start)
        except (ValueError, TypeError, KeyError):
            rule = None  # a broken imported rule shouldn't break the whole calendar
    if rule is None:
        s = event.start
        return [Occurrence(event, s, s + dur)] if _hits(s, s + dur, range_start, range_end) else []
    skip = set(event.exdates)
    out = []
    for s in rule.between(range_start - dur, range_end, inc=True):
        if s not in skip and _hits(s, s + dur, range_start, range_end):
            out.append(Occurrence(event, s, s + dur))
    return out


