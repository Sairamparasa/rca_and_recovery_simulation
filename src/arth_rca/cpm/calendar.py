"""
Calendar engine for calendar-aware CPM calculations.
Supports standard workweek patterns, shift hours, exceptions, and P6 clndr_data parsing.
"""

from datetime import datetime, date, time, timedelta
from typing import Set, Dict, Optional, Tuple
import re
from arth_rca.cpm.types import CPMCalendarInput


def parse_p6_clndr_data(clndr_data: Optional[str]) -> Tuple[Set[int], Set[date]]:
    """
    Parse native Primavera P6 clndr_data blob to extract:
    1. DaysOfWeek working pattern (0=Mon .. 6=Sun)
    2. Holiday / Exception dates (converted from Windows/Excel serial dates)
    """
    if not clndr_data:
        return {0, 1, 2, 3, 4}, set()

    working_days: Set[int] = set()
    holidays: Set[date] = set()
    
    # P6 days: 1=Sunday, 2=Monday, 3=Tuesday, 4=Wednesday, 5=Thursday, 6=Friday, 7=Saturday
    # Python weekday: Monday=0, ..., Sunday=6
    p6_to_py_weekday = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

    for p6_day in range(1, 8):
        m = re.search(rf'\(0\|\|{p6_day}\(\)\((.*?)\)\)', clndr_data, re.DOTALL)
        if m and "(s|" in m.group(1):
            working_days.add(p6_to_py_weekday[p6_day])

    if not working_days:
        working_days = {0, 1, 2, 3, 4}

    # Extract Exceptions (serial date numbers)
    for serial in re.findall(r'\(d\|(\d+)\)', clndr_data):
        dt = datetime(1899, 12, 30) + timedelta(days=int(serial))
        holidays.add(dt.date())

    return working_days, holidays


class CalendarEngine:
    """Provides pure calendar-aware date math for CPM passes."""

    def __init__(self, calendar: CPMCalendarInput):
        self.calendar = calendar
        self.working_days: Set[int] = set(calendar.working_days)  # 0=Mon, 6=Sun
        self.holidays: Set[date] = set(calendar.holidays)
        self.work_hours_per_day = max(1.0, calendar.work_hours_per_day)

    def is_work_day(self, dt: date) -> bool:
        """Check if a given calendar date is a working day."""
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
        """
        Add work duration to start_dt.
        For a 1-day task starting Monday 08:00, finish is Monday 17:00.
        For a 2-day task starting Monday 08:00, finish is Tuesday 17:00.
        For a 0-day milestone, finish is start_dt.
        """
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
        """
        Subtract work duration from end_dt.
        For Late Finish on Tuesday 17:00 with 2 days duration, Late Start is Monday 08:00.
        """
        if duration_days <= 0.0:
            return end_dt

        curr = end_dt.date()
        while not self.is_work_day(curr):
            curr -= timedelta(days=1)

        days_to_sub = int(duration_days)
        fraction = duration_days - days_to_sub

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
        """Count the number of working days difference between start_dt and end_dt."""
        d1 = start_dt.date()
        d2 = end_dt.date()

        if d1 == d2:
            return 0.0

        if d1 > d2:
            curr = d2
            count = 0
            while curr < d1:
                if self.is_work_day(curr):
                    count += 1
                curr += timedelta(days=1)
            return -float(count)

        curr = d1
        count = 0
        while curr < d2:
            if self.is_work_day(curr):
                count += 1
            curr += timedelta(days=1)
        return float(count)


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
