"""
Calendar engine for calendar-aware CPM calculations.
Supports standard workweek patterns, shift hours, exceptions, and P6 clndr_data parsing.
"""

from datetime import datetime, date, time, timedelta
from typing import Set, Dict, Optional, Tuple
from arth_rca.cpm.types import CPMCalendarInput


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

        # Ensure start_dt is on a valid work day
        curr = start_dt.date()
        while not self.is_work_day(curr):
            curr += timedelta(days=1)

        days_to_add = int(duration_days)
        fraction = duration_days - days_to_add

        # N full working days means (N - 1) day hops
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
        For Late Finish on Monday 17:00 with 1 day duration, Late Start is Monday 08:00.
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
        """
        Advance date by offset_days (used for relationship lags).
        e.g. Thu 08:00 + 1 day lag -> Fri 08:00.
        """
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
        """
        Count the number of working days difference between start_dt and end_dt.
        If start_dt.date() == end_dt.date() -> 0.0
        If end_dt > start_dt -> positive count of work days
        If start_dt > end_dt -> negative count of work days
        """
        d1 = start_dt.date()
        d2 = end_dt.date()

        if d1 == d2:
            return 0.0

        if d1 > d2:
            # Negative float
            curr = d2
            count = 0
            while curr < d1:
                if self.is_work_day(curr):
                    count += 1
                curr += timedelta(days=1)
            return -float(count)

        # Positive float
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
