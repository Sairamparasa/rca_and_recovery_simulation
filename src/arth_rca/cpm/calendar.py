"""
Calendar engine for calendar-aware CPM calculations.
Supports standard workweek patterns, shift hours, exceptions, and P6 clndr_data parsing.
"""

from datetime import datetime, date, time, timedelta
from typing import Set, Dict, Optional, Tuple
import re
from arth_rca.cpm.types import CPMCalendarInput


def parse_p6_clndr_data(clndr_data: Optional[str]) -> Tuple[Set[int], Set[date], Set[date]]:
    """
    Parse native Primavera P6 clndr_data blob to extract:
    1. DaysOfWeek working pattern (0=Mon .. 6=Sun)
    2. Holiday / Non-work Exceptions
    3. Extra Work Exceptions (non-working days made working)
    """
    if not clndr_data:
        return {0, 1, 2, 3, 4}, set(), set()

    working_days: Set[int] = set()
    holidays: Set[date] = set()
    work_exceptions: Set[date] = set()
    
    p6_to_py_weekday = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

    for p6_day in range(1, 8):
        m = re.search(rf'\(0\|\|{p6_day}\(\)\((.*?)\)\)', clndr_data, re.DOTALL)
        if m and "(s|" in m.group(1):
            working_days.add(p6_to_py_weekday[p6_day])

    if not working_days:
        working_days = {0, 1, 2, 3, 4}

    # Extract Exceptions
    for m in re.finditer(r'\(d\|(\d+)\)(.*?)\)', clndr_data, re.DOTALL):
        serial = int(m.group(1))
        body = m.group(2)
        dt = (datetime(1899, 12, 30) + timedelta(days=serial)).date()
        if "(s|" in body:
            work_exceptions.add(dt)
        else:
            holidays.add(dt)

    return working_days, holidays, work_exceptions


class CalendarEngine:
    """Provides pure calendar-aware date math for CPM passes."""

    def __init__(self, calendar: CPMCalendarInput):
        self.calendar = calendar
        self.working_days: Set[int] = set(calendar.working_days)  # 0=Mon, 6=Sun
        self.holidays: Set[date] = set(calendar.holidays)
        self.work_exceptions: Set[date] = set(getattr(calendar, "work_exceptions", set()))
        self.work_hours_per_day = max(1.0, calendar.work_hours_per_day)

    def is_work_day(self, dt: date) -> bool:
        """Check if a given calendar date is a working day."""
        if dt in self.work_exceptions:
            return True
        if dt in self.holidays:
            return False
        return dt.weekday() in self.working_days

    def align_to_work_day_start(self, dt: datetime) -> datetime:
        """Advance dt forward to the nearest working day morning."""
        curr = dt.date()
        while not self.is_work_day(curr):
            curr += timedelta(days=1)
        return datetime.combine(curr, time(8, 0))

    def align_to_work_day_end(self, dt: datetime) -> datetime:
        """Move dt backward to the nearest working day evening."""
        curr = dt.date()
        while not self.is_work_day(curr):
            curr -= timedelta(days=1)
        return datetime.combine(curr, time(17, 0))

    def add_work_days(self, start_dt: datetime, duration_days: float) -> datetime:
        """Add work duration to start_dt."""
        if duration_days <= 0.0:
            return start_dt

        curr = start_dt.date()
        while not self.is_work_day(curr):
            curr += timedelta(days=1)

        days_to_add = int(duration_days)
        fraction = duration_days - days_to_add

        remaining_hops = max(0, days_to_add - 1)
        while remaining_hops > 0:
            curr += timedelta(days=1)
            if self.is_work_day(curr):
                remaining_hops -= 1

        end_hour = 17 if fraction == 0.0 else int(8 + fraction * self.work_hours_per_day)
        return datetime.combine(curr, time(end_hour, 0))

    def subtract_work_days(self, end_dt: datetime, duration_days: float) -> datetime:
        """Subtract work duration from end_dt."""
        if duration_days <= 0.0:
            return end_dt

        curr = end_dt.date()
        while not self.is_work_day(curr):
            curr -= timedelta(days=1)

        days_to_sub = int(duration_days)
        remaining_hops = max(0, days_to_sub - 1)
        while remaining_hops > 0:
            curr -= timedelta(days=1)
            if self.is_work_day(curr):
                remaining_hops -= 1

        start_hour = 8
        return datetime.combine(curr, time(start_hour, 0))

    def advance_work_days(self, dt: datetime, offset_days: float) -> datetime:
        """Advance date by offset_days (used for relationship lags)."""
        if offset_days == 0.0:
            return dt

        curr = dt.date()
        while not self.is_work_day(curr):
            curr += timedelta(days=1)

        if offset_days > 0:
            remaining = int(offset_days)
            while remaining > 0:
                curr += timedelta(days=1)
                if self.is_work_day(curr):
                    remaining -= 1
        else:
            remaining = int(abs(offset_days))
            while remaining > 0:
                curr -= timedelta(days=1)
                if self.is_work_day(curr):
                    remaining -= 1

        return datetime.combine(curr, dt.time())

    def recede_work_days(self, dt: datetime, offset_days: float) -> datetime:
        """Recede date by offset_days."""
        return self.advance_work_days(dt, -offset_days)

    def work_days_between(self, start_dt: datetime, end_dt: datetime) -> float:
        """Count the number of working days difference between start_dt and end_dt with exact hour boundary precision."""
        if start_dt == end_dt:
            return 0.0

        is_neg = False
        if start_dt > end_dt:
            is_neg = True
            t_start, t_end = end_dt, start_dt
        else:
            t_start, t_end = start_dt, end_dt

        curr = t_start.date()
        if t_start.hour >= 17:
            curr += timedelta(days=1)

        stop_date = t_end.date()
        if t_end.hour >= 17:
            stop_date += timedelta(days=1)

        count = 0
        while curr < stop_date:
            if self.is_work_day(curr):
                count += 1
            curr += timedelta(days=1)

        return -float(count) if is_neg else float(count)


def build_calendar_engine_map(calendars: Dict[int, CPMCalendarInput]) -> Dict[int, CalendarEngine]:
    """Factory creating CalendarEngine instances for all calendars in a project."""
    engine_map: Dict[int, CalendarEngine] = {}
    default_engine = None

    for clndr_id, clndr in calendars.items():
        engine = CalendarEngine(clndr)
        engine_map[clndr_id] = engine
        if default_engine is None:
            default_engine = engine

    if default_engine is None:
        default_engine = CalendarEngine(CPMCalendarInput(clndr_id=0))
        engine_map[0] = default_engine

    return engine_map
