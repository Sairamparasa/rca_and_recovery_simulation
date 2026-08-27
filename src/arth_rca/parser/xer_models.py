"""
Data models representing tables and records within a Primavera P6 XER export file.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any


def parse_p6_date(val: Optional[str]) -> Optional[datetime]:
    """Parse standard P6 XER date string (YYYY-MM-DD HH:MM:SS or YYYY-MM-DD HH:MM)."""
    if not val or not val.strip():
        return None
    val = val.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%b-%y %H:%M",
        "%d-%b-%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def parse_float(val: Optional[str], default: float = 0.0) -> float:
    """Parse numeric float from string."""
    if val is None or not str(val).strip():
        return default
    try:
        return float(str(val).strip())
    except ValueError:
        return default


def parse_int(val: Optional[str], default: int = 0) -> int:
    """Parse integer from string."""
    if val is None or not str(val).strip():
        return default
    try:
        return int(str(val).strip())
    except ValueError:
        return default


def parse_bool(val: Optional[str]) -> bool:
    """Parse P6 boolean (Y/N or 1/0 or True/False)."""
    if not val:
        return False
    return str(val).strip().upper() in ("Y", "1", "TRUE")


@dataclass
class XERProject:
    proj_id: int
    proj_short_name: str
    clndr_id: Optional[int] = None
    plan_start_date: Optional[datetime] = None
    plan_end_date: Optional[datetime] = None
    must_finish_by_date: Optional[datetime] = None
    last_recalc_date: Optional[datetime] = None
    f_calc_mode: str = "START_DATES"  # START_DATES (CS_Start), FINISH_DATES (CS_Finish), MIN_START_FINISH (CS_Min)
    oos_mode: str = "RETAINED_LOGIC"  # RETAINED_LOGIC (RL), PROGRESS_OVERRIDE (PO), ACTUAL_DATES (AD)
    critical_path_type: str = "TOTAL_FLOAT"  # TOTAL_FLOAT, LONGEST_PATH
    critical_float_hr_cnt: float = 0.0
    use_expect_end_flag: bool = False
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERCalendar:
    clndr_id: int
    clndr_name: str
    default_flag: bool = False
    clndr_type: str = "CA_Base"  # CA_Base, CA_Project, CA_Resource
    day_hr_cnt: float = 8.0
    week_hr_cnt: float = 40.0
    month_hr_cnt: float = 173.33
    year_hr_cnt: float = 2080.0
    clndr_data: Optional[str] = None  # Raw holiday & shift definitions
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERWBS:
    wbs_id: int
    proj_id: int
    wbs_short_name: str
    wbs_name: str
    parent_wbs_id: Optional[int] = None
    seq_num: int = 0
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERTask:
    task_id: int
    proj_id: int
    wbs_id: int
    clndr_id: int
    task_code: str
    task_name: str
    task_type: str = "TT_Task"  # TT_Task, TT_Mile, TT_FinMile, TT_LOE, TT_WBS
    status_code: str = "TK_NotStart"  # TK_NotStart, TK_Active, TK_Complete
    
    # Durations (in hours)
    target_durn_hr_cnt: float = 0.0  # Original duration
    remain_durn_hr_cnt: float = 0.0  # Remaining duration
    act_work_qty: float = 0.0
    phys_complete_pct: float = 0.0
    
    # Dates
    target_start_date: Optional[datetime] = None
    target_end_date: Optional[datetime] = None
    early_start_date: Optional[datetime] = None
    early_end_date: Optional[datetime] = None
    late_start_date: Optional[datetime] = None
    late_end_date: Optional[datetime] = None
    act_start_date: Optional[datetime] = None
    act_end_date: Optional[datetime] = None
    restart_date: Optional[datetime] = None
    reend_date: Optional[datetime] = None
    expect_end_date: Optional[datetime] = None
    
    # Float & Logic
    total_float_hr_cnt: float = 0.0
    free_float_hr_cnt: float = 0.0
    driving_path_flag: bool = False
    
    # Constraints (Primary & Secondary)
    cstr_type: Optional[str] = None  # CS_MANDSTART, CS_MANDEND, CS_START, CS_FINISH, CS_SSO, CS_SSB, CS_FSO, CS_FSB, CS_ALAP
    cstr_date: Optional[datetime] = None
    cstr_type2: Optional[str] = None
    cstr_date2: Optional[datetime] = None
    
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERPredecessor:
    task_pred_id: int
    task_id: int        # Successor
    pred_task_id: int   # Predecessor
    proj_id: int
    pred_type: str = "PR_FS"  # PR_FS, PR_SS, PR_FF, PR_SF
    lag_hr_cnt: float = 0.0
    comments: Optional[str] = None
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERResource:
    rsrc_id: int
    rsrc_short_name: str
    rsrc_name: str
    rsrc_type: str = "RT_Labor"
    clndr_id: Optional[int] = None
    unit_of_measure: Optional[str] = None
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERTaskResource:
    taskrsrc_id: int
    task_id: int
    proj_id: int
    rsrc_id: int
    target_qty: float = 0.0
    target_cost: float = 0.0
    remain_qty: float = 0.0
    remain_cost: float = 0.0
    act_qty: float = 0.0
    act_cost: float = 0.0
    raw_fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class XERParsedFile:
    header: str
    projects: Dict[int, XERProject] = field(default_factory=dict)
    calendars: Dict[int, XERCalendar] = field(default_factory=dict)
    wbs: Dict[int, XERWBS] = field(default_factory=dict)
    tasks: Dict[int, XERTask] = field(default_factory=dict)
    predecessors: List[XERPredecessor] = field(default_factory=list)
    resources: Dict[int, XERResource] = field(default_factory=dict)
    task_resources: List[XERTaskResource] = field(default_factory=list)
    raw_tables: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
