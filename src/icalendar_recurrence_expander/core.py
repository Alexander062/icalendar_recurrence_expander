from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterator, Optional


@dataclass(frozen=True)
class RecurrenceRule:
    """A parsed RRULE value.

    Only the subset of RFC 5545 needed for the common cases is supported:
    FREQ, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH, BYSETPOS, WKST.
    Unsupported parts raise ValueError at parse time rather than being silently
    dropped, so callers know exactly what they are getting.
    """
    freq: str
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    byday: tuple[str, ...] = ()
    bymonthday: tuple[int, ...] = ()
    bymonth: tuple[int, ...] = ()
    bysetpos: tuple[int, ...] = ()
    wkst: str = "MO"

    _WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

    def _weekday_index(self, token: str) -> int:
        return self._WEEKDAYS[token]


def _parse_dt(value: str) -> datetime:
    """Parse an iCalendar datetime or date string into a naive datetime.

    iCalendar datetimes may carry a trailing Z (UTC) or be local. We strip the
    Z and return a naive datetime; callers comparing UNTIL against instances
    should ensure both sides are naive. This is a deliberate simplification —
    full timezone handling is out of scope.
    """
    v = value.strip().upper()
    if v.endswith("Z"):
        v = v[:-1]
    if "T" in v:
        return datetime.strptime(v, "%Y%m%dT%H%M%S")
    d = datetime.strptime(v, "%Y%m%d")
    return d


def parse_rrule(value: str) -> RecurrenceRule:
    """Parse an RRULE value string into a RecurrenceRule.

    Accepts either a bare value ("FREQ=DAILY;INTERVAL=2") or a line including
    the RRULE: prefix. Unknown parts raise ValueError so callers never get a
    rule that silently ignores something they specified.
    """
    v = value.strip()
    if v.upper().startswith("RRULE:"):
        v = v[len("RRULE:"):]
    parts = [p for p in v.split(";") if p]
    if not parts:
        raise ValueError("empty RRULE")
    fields: dict[str, str] = {}
    for p in parts:
        if "=" not in p:
            raise ValueError(f"malformed RRULE part: {p!r}")
        k, val = p.split("=", 1)
        fields[k.upper()] = val
    if "FREQ" not in fields:
        raise ValueError("RRULE missing FREQ")
    freq = fields["FREQ"].upper()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        raise ValueError(f"unsupported FREQ: {freq}")
    interval = int(fields.get("INTERVAL", "1"))
    if interval < 1:
        raise ValueError("INTERVAL must be >= 1")
    count: Optional[int] = None
    if "COUNT" in fields:
        count = int(fields["COUNT"])
        if count < 1:
            raise ValueError("COUNT must be >= 1")
    until: Optional[datetime] = None
    if "UNTIL" in fields:
        until = _parse_dt(fields["UNTIL"])
    if count is not None and until is not None:
        raise ValueError("RRULE cannot have both COUNT and UNTIL")
    byday = tuple(x.upper() for x in fields["BYDAY"].split(",")) if "BYDAY" in fields else ()
    for d in byday:
        if not re.fullmatch(r"-?[1-5]?[A-Z]{2}", d):
            raise ValueError(f"invalid BYDAY token: {d!r}")
    bymonthday = tuple(int(x) for x in fields["BYMONTHDAY"].split(",")) if "BYMONTHDAY" in fields else ()
    bymonth = tuple(int(x) for x in fields["BYMONTH"].split(",")) if "BYMONTH" in fields else ()
    bysetpos = tuple(int(x) for x in fields["BYSETPOS"].split(",")) if "BYSETPOS" in fields else ()
    wkst = fields.get("WKST", "MO").upper()
    if wkst not in RecurrenceRule._WEEKDAYS:
        raise ValueError(f"invalid WKST: {wkst}")
    known = {"FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH", "BYSETPOS", "WKST"}
    unknown = set(fields) - known
    if unknown:
        raise ValueError(f"unsupported RRULE parts: {sorted(unknown)}")
    return RecurrenceRule(freq=freq, interval=interval, count=count, until=until,
                          byday=byday, bymonthday=bymonthday, bymonth=bymonth,
                          bysetpos=bysetpos, wkst=wkst)


def _iter_daily(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    cur = dtstart
    step = timedelta(days=rule.interval)
    while True:
        yield cur
        cur = cur + step


def _iter_weekly(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    """Yield weekly occurrences.

    If BYDAY is given, each interval produces one occurrence per listed weekday
    that falls at or after dtstart within that week. We anchor weeks on WKST so
    that INTERVAL>1 skips the correct block of days.
    """
    if not rule.byday:
        yield from _iter_daily_like_weekly(rule, dtstart)
        return
    target_wd = sorted(rule._weekday_index(d.lstrip("-+").rstrip("0123456789") or d) for d in rule.byday)
    wkst_idx = rule._weekday_index(rule.wkst)
    # Find the start of the week containing dtstart.
    delta = (dtstart.weekday() - wkst_idx) % 7
    week_start = dtstart - timedelta(days=delta)
    step_days = 7 * rule.interval
    first = True
    while True:
        for wd in target_wd:
            offset = (wd - wkst_idx) % 7
            cand = week_start + timedelta(days=offset)
            if cand < dtstart:
                continue
            yield cand
        week_start = week_start + timedelta(days=step_days)
        first = False


def _iter_daily_like_weekly(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    cur = dtstart
    step = timedelta(days=7 * rule.interval)
    while True:
        yield cur
        cur = cur + step


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        nxt = datetime(year + 1, 1, 1)
    else:
        nxt = datetime(year, month + 1, 1)
    return (nxt - datetime(year, month, 1)).days


def _resolve_monthday(year: int, month: int, day: int) -> Optional[int]:
    """Resolve a possibly-negative BYMONTHDAY to a concrete day, or None if invalid."""
    dim = _days_in_month(year, month)
    if day > 0:
        return day if day <= dim else None
    if day < 0:
        concrete = dim + day + 1
        return concrete if 1 <= concrete <= dim else None
    return None


def _iter_monthly(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    """Yield monthly occurrences.

    Without BYMONTHDAY, we keep the day-of-month of dtstart (clamping short
    months by skipping them — Feb 30 never fires). With BYMONTHDAY we emit one
    occurrence per listed day per month. BYSETPOS selects from the month's
    candidates by position.
    """
    year, month = dtstart.year, dtstart.month
    base_day = dtstart.day
    time_part = dtstart.replace(day=1) - datetime(year, month, 1)
    count = 0
    while True:
        if rule.bymonth and month not in rule.bymonth:
            year, month = _advance_month(year, month, 1)
            continue
        candidates: list[datetime] = []
        days = rule.bymonthday if rule.bymonthday else (base_day,)
        for d in days:
            concrete = _resolve_monthday(year, month, d)
            if concrete is None:
                continue
            cand = datetime(year, month, concrete, dtstart.hour, dtstart.minute,
                            dtstart.second, dtstart.microsecond)
            if cand < dtstart:
                continue
            candidates.append(cand)
        candidates.sort()
        if rule.bysetpos:
            dim = _days_in_month(year, month)
            selected: list[datetime] = []
            for pos in rule.bysetpos:
                idx = pos - 1 if pos > 0 else len(candidates) + pos
                if 0 <= idx < len(candidates):
                    selected.append(candidates[idx])
            candidates = sorted(set(selected))
        for c in candidates:
            yield c
        year, month = _advance_month(year, month, rule.interval)


def _advance_month(year: int, month: int, step: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + step
    return total // 12, total % 12 + 1


def _iter_yearly(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    """Yearly occurrences.

    Without BYMONTH, the event recurs on the same month/day each year. With
    BYMONTH, only those months are considered. BYMONTHDAY overrides the day.
    """
    year = dtstart.year
    months = rule.bymonth if rule.bymonth else (dtstart.month,)
    while True:
        for m in sorted(months):
            day = dtstart.day
            if rule.bymonthday:
                days = [d for d in rule.bymonthday]
                for d in days:
                    concrete = _resolve_monthday(year, m, d)
                    if concrete is None:
                        continue
                    cand = datetime(year, m, concrete, dtstart.hour, dtstart.minute,
                                    dtstart.second, dtstart.microsecond)
                    if cand >= dtstart:
                        yield cand
            else:
                concrete = _resolve_monthday(year, m, day)
                if concrete is None:
                    continue
                cand = datetime(year, m, concrete, dtstart.hour, dtstart.minute,
                                dtstart.second, dtstart.microsecond)
                if cand >= dtstart:
                    yield cand
        year += rule.interval


def _iter(rule: RecurrenceRule, dtstart: datetime) -> Iterator[datetime]:
    if rule.freq == "DAILY":
        return _iter_daily(rule, dtstart)
    if rule.freq == "WEEKLY":
        return _iter_weekly(rule, dtstart)
    if rule.freq == "MONTHLY":
        return _iter_monthly(rule, dtstart)
    return _iter_yearly(rule, dtstart)


def expand_recurrence(dtstart: datetime, rrule: str | RecurrenceRule,
                      range_start: datetime, range_end: datetime) -> list[datetime]:
    """Expand an RRULE into concrete datetimes within [range_start, range_end].

    dtstart is the first occurrence (it is always included if it falls in
    range). rrule may be a string or a pre-parsed RecurrenceRule. The returned
    list is sorted ascending. range_end is inclusive.

    A safety cap of 100000 generated occurrences prevents runaway loops on
    pathological rules (e.g. FREQ=DAILY;INTERVAL=1 with no COUNT/UNTIL and a
    range that never matches); reaching it raises RuntimeError.
    """
    if isinstance(rrule, str):
        rule = parse_rrule(rrule)
    else:
        rule = rrule
    if range_end < range_start:
        return []
    results: list[datetime] = []
    emitted = 0
    cap = 100000
    for occ in _iter(rule, dtstart):
        emitted += 1
        if emitted > cap:
            raise RuntimeError("recurrence expansion exceeded safety cap")
        if occ > range_end:
            break
        if rule.until is not None and occ > rule.until:
            break
        if occ >= range_start:
            results.append(occ)
        if rule.count is not None and len(results) >= rule.count:
            break
    # COUNT limits total occurrences from dtstart, not just those in range.
    # We must count from dtstart, so re-run with proper accounting if COUNT set.
    if rule.count is not None:
        results = []
        total = 0
        for occ in _iter(rule, dtstart):
            total += 1
            if occ > range_end or (rule.until is not None and occ > rule.until):
                break
            if occ >= range_start:
                results.append(occ)
            if total >= rule.count:
                break
    results.sort()
    return results
