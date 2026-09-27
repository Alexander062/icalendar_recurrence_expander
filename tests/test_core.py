import unittest
from datetime import datetime

from icalendar_recurrence_expander import expand_recurrence, parse_rrule, RecurrenceRule


class TestParseRRule(unittest.TestCase):
    def test_basic_daily(self):
        r = parse_rrule("FREQ=DAILY;INTERVAL=2")
        self.assertEqual(r.freq, "DAILY")
        self.assertEqual(r.interval, 2)
        self.assertIsNone(r.count)
        self.assertIsNone(r.until)

    def test_strips_rrule_prefix(self):
        r = parse_rrule("RRULE:FREQ=WEEKLY;BYDAY=MO,WE")
        self.assertEqual(r.freq, "WEEKLY")
        self.assertEqual(r.byday, ("MO", "WE"))

    def test_until_with_z(self):
        r = parse_rrule("FREQ=DAILY;UNTIL=20200101T000000Z")
        self.assertEqual(r.until, datetime(2020, 1, 1))

    def test_until_date_only(self):
        r = parse_rrule("FREQ=DAILY;UNTIL=20200101")
        self.assertEqual(r.until, datetime(2020, 1, 1))

    def test_count_and_until_conflict(self):
        with self.assertRaises(ValueError):
            parse_rrule("FREQ=DAILY;COUNT=3;UNTIL=20200101")

    def test_missing_freq(self):
        with self.assertRaises(ValueError):
            parse_rrule("INTERVAL=2")

    def test_unknown_part_raises(self):
        with self.assertRaises(ValueError):
            parse_rrule("FREQ=DAILY;BYYEARDAY=1")

    def test_invalid_freq(self):
        with self.assertRaises(ValueError):
            parse_rrule("FREQ=HOURLY")

    def test_negative_interval(self):
        with self.assertRaises(ValueError):
            parse_rrule("FREQ=DAILY;INTERVAL=0")


class TestExpandDaily(unittest.TestCase):
    def test_daily_in_range(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY", datetime(2020, 1, 3), datetime(2020, 1, 5, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 3, 9, 0), datetime(2020, 1, 4, 9, 0), datetime(2020, 1, 5, 9, 0)])

    def test_daily_interval(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY;INTERVAL=2", datetime(2020, 1, 1), datetime(2020, 1, 7, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 1, 9, 0), datetime(2020, 1, 3, 9, 0), datetime(2020, 1, 5, 9, 0), datetime(2020, 1, 7, 9, 0)])

    def test_count_limits_total(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY;COUNT=3", datetime(2020, 1, 2), datetime(2020, 1, 10))
        # dtstart is occurrence 1, Jan 2 is occurrence 2, Jan 3 is occurrence 3.
        self.assertEqual(results, [datetime(2020, 1, 2, 9, 0), datetime(2020, 1, 3, 9, 0)])

    def test_until_stops(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY;UNTIL=20200103T090000", datetime(2020, 1, 1), datetime(2020, 1, 10))
        self.assertEqual(results, [datetime(2020, 1, 1, 9, 0), datetime(2020, 1, 2, 9, 0), datetime(2020, 1, 3, 9, 0)])


class TestExpandWeekly(unittest.TestCase):
    def test_weekly_byday(self):
        dtstart = datetime(2020, 1, 1, 10, 0)  # Wednesday
        results = expand_recurrence(dtstart, "FREQ=WEEKLY;BYDAY=MO,WE,FR", datetime(2020, 1, 1), datetime(2020, 1, 10, 23, 59, 59))
        self.assertEqual(results, [
            datetime(2020, 1, 1, 10, 0),   # Wed
            datetime(2020, 1, 3, 10, 0),   # Fri
            datetime(2020, 1, 6, 10, 0),   # Mon
            datetime(2020, 1, 8, 10, 0),   # Wed
            datetime(2020, 1, 10, 10, 0),  # Fri
        ])

    def test_weekly_interval_skips_week(self):
        dtstart = datetime(2020, 1, 6, 10, 0)  # Monday
        results = expand_recurrence(dtstart, "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO", datetime(2020, 1, 6), datetime(2020, 2, 3, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 6, 10, 0), datetime(2020, 1, 20, 10, 0), datetime(2020, 2, 3, 10, 0)])

    def test_weekly_no_byday(self):
        dtstart = datetime(2020, 1, 1, 10, 0)
        results = expand_recurrence(dtstart, "FREQ=WEEKLY", datetime(2020, 1, 1), datetime(2020, 1, 22, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 1, 10, 0), datetime(2020, 1, 8, 10, 0), datetime(2020, 1, 15, 10, 0), datetime(2020, 1, 22, 10, 0)])


class TestExpandMonthly(unittest.TestCase):
    def test_monthly_basic(self):
        dtstart = datetime(2020, 1, 15, 12, 0)
        results = expand_recurrence(dtstart, "FREQ=MONTHLY", datetime(2020, 1, 1), datetime(2020, 4, 30, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 15, 12, 0), datetime(2020, 2, 15, 12, 0), datetime(2020, 3, 15, 12, 0), datetime(2020, 4, 15, 12, 0)])

    def test_monthly_feb_30_skipped(self):
        dtstart = datetime(2020, 1, 30, 12, 0)
        results = expand_recurrence(dtstart, "FREQ=MONTHLY", datetime(2020, 1, 1), datetime(2020, 4, 30, 23, 59, 59))
        # Jan 30, Feb has no 30th (skipped), Mar 30, Apr 30.
        self.assertEqual(results, [datetime(2020, 1, 30, 12, 0), datetime(2020, 3, 30, 12, 0), datetime(2020, 4, 30, 12, 0)])

    def test_monthly_bymonthday_negative(self):
        dtstart = datetime(2020, 1, 31, 12, 0)
        results = expand_recurrence(dtstart, "FREQ=MONTHLY;BYMONTHDAY=-1", datetime(2020, 1, 1), datetime(2020, 3, 31, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 31, 12, 0), datetime(2020, 2, 29, 12, 0), datetime(2020, 3, 31, 12, 0)])

    def test_monthly_interval(self):
        dtstart = datetime(2020, 1, 15, 12, 0)
        results = expand_recurrence(dtstart, "FREQ=MONTHLY;INTERVAL=2", datetime(2020, 1, 1), datetime(2020, 5, 30, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 15, 12, 0), datetime(2020, 3, 15, 12, 0), datetime(2020, 5, 15, 12, 0)])


class TestExpandYearly(unittest.TestCase):
    def test_yearly_basic(self):
        dtstart = datetime(2020, 3, 1, 8, 0)
        results = expand_recurrence(dtstart, "FREQ=YEARLY", datetime(2020, 1, 1), datetime(2023, 12, 31, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 3, 1, 8, 0), datetime(2021, 3, 1, 8, 0), datetime(2022, 3, 1, 8, 0), datetime(2023, 3, 1, 8, 0)])

    def test_yearly_leap_day(self):
        dtstart = datetime(2020, 2, 29, 8, 0)
        results = expand_recurrence(dtstart, "FREQ=YEARLY", datetime(2020, 1, 1), datetime(2025, 12, 31, 23, 59, 59))
        # 2020 leap, 2021 no, 2022 no, 2023 no, 2024 leap.
        self.assertEqual(results, [datetime(2020, 2, 29, 8, 0), datetime(2024, 2, 29, 8, 0)])


class TestEdgeCases(unittest.TestCase):
    def test_dtstart_before_range(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY", datetime(2020, 1, 5), datetime(2020, 1, 6, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 5, 9, 0), datetime(2020, 1, 6, 9, 0)])

    def test_empty_range(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY", datetime(2020, 2, 1), datetime(2020, 1, 1))
        self.assertEqual(results, [])

    def test_pre_parsed_rule(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        rule = RecurrenceRule(freq="DAILY", interval=3)
        results = expand_recurrence(dtstart, rule, datetime(2020, 1, 1), datetime(2020, 1, 10, 23, 59, 59))
        self.assertEqual(results, [datetime(2020, 1, 1, 9, 0), datetime(2020, 1, 4, 9, 0), datetime(2020, 1, 7, 9, 0), datetime(2020, 1, 10, 9, 0)])

    def test_range_end_inclusive(self):
        dtstart = datetime(2020, 1, 1, 9, 0)
        results = expand_recurrence(dtstart, "FREQ=DAILY", datetime(2020, 1, 3, 9, 0), datetime(2020, 1, 3, 9, 0))
        self.assertEqual(results, [datetime(2020, 1, 3, 9, 0)])


if __name__ == "__main__":
    unittest.main()
