"""
Unit tests for CalendarEngine arithmetic.
"""

from datetime import datetime, date
from arth_rca.cpm.types import CPMCalendarInput
from arth_rca.cpm.calendar import CalendarEngine


def test_standard_5day_calendar_add_days():
    # 5-day calendar: Mon-Fri
    cal = CalendarEngine(CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4}))

    # Mon Sep 1 2026 08:00 + 2 days -> Tue Sep 2 17:00
    mon = datetime(2026, 9, 1, 8, 0)
    tue = cal.add_work_days(mon, 2.0)
    assert tue.date() == date(2026, 9, 2)
    assert tue.hour == 17

    # Fri Sep 5 2026 08:00 + 2 days -> Mon Sep 8 17:00 (skips Sat & Sun)
    fri = datetime(2026, 9, 5, 8, 0)
    res_mon = cal.add_work_days(fri, 2.0)
    assert res_mon.date() == date(2026, 9, 8)
    assert res_mon.hour == 17


def test_holiday_skipping():
    # Labor day holiday on Mon Sep 7 2026
    holiday = date(2026, 9, 7)
    cal = CalendarEngine(CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4}, holidays={holiday}))

    fri = datetime(2026, 9, 4, 8, 0)
    # 2 days starting Friday -> skips weekend AND Monday holiday -> finishes Tuesday evening
    res = cal.add_work_days(fri, 2.0)
    assert res.date() == date(2026, 9, 8)
