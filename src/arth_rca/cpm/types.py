"""
Typed immutable data structures for the pure-function CPM engine.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List, Set
from enum import Enum


class FloatCalcMode(str, Enum):
    START_DATES = "START_DATES"          # TF = LS - ES
    FINISH_DATES = "FINISH_DATES"        # TF = LF - EF
    MIN_START_FINISH = "MIN_START_FINISH"  # TF = min(LS - ES, LF - EF)


class OOSMode(str, Enum):
    RETAINED_LOGIC = "RETAINED_LOGIC"
    PROGRESS_OVERRIDE = "PROGRESS_OVERRIDE"
    ACTUAL_DATES = "ACTUAL_DATES"


class CriticalPathType(str, Enum):
    TOTAL_FLOAT = "TOTAL_FLOAT"
    LONGEST_PATH = "LONGEST_PATH"


class DrivingStatus(str, Enum):
    DRIVING = "DRIVING"
    NON_DRIVING = "NON_DRIVING"
    OVERRIDDEN_BY_ACTUAL_DATE = "OVERRIDDEN_BY_ACTUAL_DATE"


@dataclass(frozen=True)
class CPMActivityInput:
    task_id: int
    task_code: str
    calendar_id: int
    original_duration_days: float
    remaining_duration_days: float
    status: str = "NOT_STARTED"  # NOT_STARTED, IN_PROGRESS, COMPLETED
    act_start_date: Optional[datetime] = None
    act_finish_date: Optional[datetime] = None
    
    # Constraints
    cstr_type: Optional[str] = None
    cstr_date: Optional[datetime] = None
    cstr_type2: Optional[str] = None
    cstr_date2: Optional[datetime] = None
    is_milestone: bool = False


@dataclass(frozen=True)
class CPMRelationshipInput:
    rel_id: int
    pred_task_id: int
    succ_task_id: int
    rel_type: str = "FS"  # FS, SS, FF, SF
    lag_days: float = 0.0


@dataclass(frozen=True)
class CPMCalendarInput:
    clndr_id: int
    name: str = "Standard 5-Day"
    working_days: Set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})  # Monday=0 .. Friday=4
    work_hours_per_day: float = 8.0
    holidays: Set[date] = field(default_factory=set)


@dataclass(frozen=True)
class CPMOptions:
    data_date: datetime
    f_calc_mode: FloatCalcMode = FloatCalcMode.START_DATES
    oos_mode: OOSMode = OOSMode.RETAINED_LOGIC
    critical_path_type: CriticalPathType = CriticalPathType.TOTAL_FLOAT
    critical_float_threshold_days: float = 0.0
    must_finish_by_date: Optional[datetime] = None


@dataclass(frozen=True)
class CPMActivityResult:
    task_id: int
    task_code: str
    early_start: datetime
    early_finish: datetime
    late_start: datetime
    late_finish: datetime
    total_float_days: float
    free_float_days: float
    is_critical: bool
    driving_path_flag: bool


@dataclass(frozen=True)
class CPMRelationshipResult:
    rel_id: int
    pred_task_id: int
    succ_task_id: int
    rel_type: str
    lag_days: float
    is_driving: bool
    driving_status: DrivingStatus


@dataclass(frozen=True)
class CPMResult:
    activities: Dict[int, CPMActivityResult]
    relationships: Dict[int, CPMRelationshipResult]
    project_early_finish: datetime
    project_late_finish: datetime
    longest_path_task_ids: List[int]
