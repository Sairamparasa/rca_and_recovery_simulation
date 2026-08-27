"""
Recovery Levers Library for What-If Simulation.
Defines operations on cloned schedule graphs:
- Crash: Reduce duration by N days or percentage.
- FastTrack: FS -> SS conversion or lag reduction (STRICTLY guarded by is_fasttrack_candidate).
- LogicChange: Add/remove/modify relationships (Requires PM approval tracking).
- ConstraintRelaxation: Relax/remove hard constraints (Requires PM approval tracking).
- Resequencing: Reorder independent tasks (STRICTLY guarded by transitive dependency check).
- CalendarChange: Reassign to higher capacity calendar (e.g. 5-day -> 6-day).
- ActivitySplit: Divide into parallel sub-activities.
"""

from typing import Dict, List, Optional, Set, Any, Union, Literal
from pydantic import BaseModel, Field
import networkx as nx

from arth_rca.analytics.classification import is_fasttrack_candidate
from arth_rca.db.models import generate_relationship_key


class SafetyViolationError(Exception):
    """Raised when a fast-track or unsafe recovery lever violates physical or safety gates."""
    pass


class CombinatorialConflictError(Exception):
    """Raised when multiple levers in a scenario conflict with each other or create graph cycles."""
    pass


class DependencyViolationError(Exception):
    """Raised when resequencing or logic change violates transitive dependencies."""
    pass


class BaseLever(BaseModel):
    lever_type: str
    description: str = ""
    cost_delta: float = 0.0
    requires_pm_approval: bool = False
    approved_by: Optional[str] = None


class CrashLever(BaseLever):
    lever_type: Literal["CRASH"] = "CRASH"
    task_code: str
    reduction_days: float = Field(gt=0.0)


class FastTrackLever(BaseLever):
    lever_type: Literal["FAST_TRACK"] = "FAST_TRACK"
    pred_task_code: str
    succ_task_code: str
    new_relationship_type: Literal["SS", "FS"] = "SS"
    new_lag_days: float = Field(default=0.0, ge=0.0)


class LogicChangeLever(BaseLever):
    lever_type: Literal["LOGIC_CHANGE"] = "LOGIC_CHANGE"
    action: Literal["ADD", "REMOVE", "MODIFY"] = "MODIFY"
    pred_task_code: str
    succ_task_code: str
    relationship_type: str = "FS"
    lag_days: float = 0.0
    requires_pm_approval: bool = True


class ConstraintRelaxationLever(BaseLever):
    lever_type: Literal["CONSTRAINT_RELAXATION"] = "CONSTRAINT_RELAXATION"
    task_code: str
    action: Literal["REMOVE", "RELAX_DATE"] = "REMOVE"
    new_constraint_date: Optional[str] = None
    requires_pm_approval: bool = True


class ResequencingLever(BaseLever):
    lever_type: Literal["RESEQUENCING"] = "RESEQUENCING"
    task_a_code: str
    task_b_code: str
    new_order: Literal["A_THEN_B", "B_THEN_A", "PARALLEL"] = "PARALLEL"
    requires_pm_approval: bool = True


class CalendarChangeLever(BaseLever):
    lever_type: Literal["CALENDAR_CHANGE"] = "CALENDAR_CHANGE"
    task_code: str
    new_calendar_id: int


class ActivitySplitLever(BaseLever):
    lever_type: Literal["ACTIVITY_SPLIT"] = "ACTIVITY_SPLIT"
    task_code: str
    split_count: int = Field(default=2, ge=2, le=5)


# Union type for all lever models
AnyLever = Union[
    CrashLever,
    FastTrackLever,
    LogicChangeLever,
    ConstraintRelaxationLever,
    ResequencingLever,
    CalendarChangeLever,
    ActivitySplitLever,
]


def validate_transitive_independence(graph: nx.DiGraph, task_a: int, task_b: int) -> bool:
    """
    Ensure task_a and task_b have NO transitive path in either direction.
    """
    if task_a == task_b:
        return False
    if not graph.has_node(task_a) or not graph.has_node(task_b):
        return False
    if nx.has_path(graph, task_a, task_b) or nx.has_path(graph, task_b, task_a):
        return False
    return True
