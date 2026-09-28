# iCalendar Recurrence Expander

Expands RRULE recurrence rules from iCalendar data into concrete datetime instances within a given range. Standard library only, no dependencies.

## Usage

```python
from datetime import datetime
from icalendar_recurrence_expander import expand_recurrence, parse_rrule, RecurrenceRule

dtstart = datetime(2020, 1, 1, 9, 0)
occurrences = expand_recurrence(
    dtstart,
    "FREQ=DAILY;INTERVAL=2",
    datetime(2020, 1, 1),
    datetime(2020, 1, 10),
)
# [datetime(2020, 1, 1, 9, 0), datetime(2020, 1, 3, 9, 0), ...]

# or pre-parse for reuse
rule = parse_rrule("FREQ=WEEKLY;BYDAY=MO,WE")
occurrences = expand_recurrence(dtstart, rule, datetime(2020, 1, 1), datetime(2020, 1, 31))
```

## Why

The problem: you have iCalendar RRULE strings and need the actual datetimes, without pulling in a heavy dependency. This library covers the common cases (DAILY, WEEKLY, MONTHLY, YEARLY with INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH, BYSETPOS) and nothing more. The trade-off is that timezone-aware datetimes are not supported — `UNTIL` values with a trailing `Z` are parsed as naive UTC and compared as naive. If you need real timezone math, convert before calling.

## Edge cases you will hit

- **Feb 30 is silently skipped.** A monthly rule on day 30 simply produces no occurrence in February. This matches RFC 5545's "skip invalid dates" behaviour rather than clamping.
- **COUNT counts from dtstart, not from range_start.** If `COUNT=5` and your range starts at the third occurrence, you get three results, not five.
- **Negative BYMONTHDAY** (`-1` for last day of month) is supported; days that don't exist in a given month are skipped.
- **Unsupported RRULE parts raise ValueError** at parse time rather than being silently ignored. If you pass `BYHOUR`, you get an error, not a surprise.

## Exports

- `expand_recurrence(dtstart, rrule, range_start, range_end) -> list[datetime]`
- `parse_rrule(value: str) -> RecurrenceRule`
- `RecurrenceRule` (dataclass with fields: `freq`, `interval`, `count`, `until`, `byday`, `bymonthday`, `bymonth`, `bysetpos`, `wkst`)
