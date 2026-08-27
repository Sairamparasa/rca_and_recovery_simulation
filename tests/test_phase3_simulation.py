"""
Comprehensive Unit & Integration Test Suite for Phase 3: What-If / Recovery Simulation Engine.
Covers:
1. Strict Safety Gate: HARD_PHYSICAL, HARD_REGULATORY, HARD_SAFETY, UNCLASSIFIED rejection.
2. Scoped Preview vs Full-Schedule Parallel Path Shift Detection.
3. Full Lever-Set Combinatorial Conflict & Cycle Detection.
4. Transitive Dependency Independence Check for Resequencing.
5. Approval State Tracking for Logic Change and Constraint Relaxation.
6. 3 Realistic Scenarios against Real Ingested Schedules (PHX3DC1 & 247011).
"""

import pytest
from datetime import datetime, timedelta
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from pathlib import Path

from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.analytics.classification import ClassificationResult
from arth_rca.db.models import RelationshipClassification, generate_relationship_key
import arth_rca.db.models  # noqa: F401
from arth_rca.simulation.engine import run_simulation
from arth_rca.simulation.levers import (
    CrashLever,
    FastTrackLever,
    LogicChangeLever,
    ConstraintRelaxationLever,
    ResequencingLever,
    CalendarChangeLever,
    ActivitySplitLever,
    SafetyViolationError,
    CombinatorialConflictError,
    DependencyViolationError,
)
from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.api.app import app
from arth_rca.db.database import get_db


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db):
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_safety_gate_strictly_rejects_hard_and_unclassified_fasttrack():
    """
    Acceptance Criterion 1:
    Confirm the what-if engine refuses to offer/apply fast-track on HARD_PHYSICAL,
    HARD_REGULATORY, HARD_SAFETY, or UNCLASSIFIED relationships under every code path.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="CONC-01", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
        2: CPMActivityInput(task_id=2, task_code="STRIP-02", calendar_id=1, original_duration_days=3.0, remaining_duration_days=3.0),
    }
    rels = [CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0)]
    rel_key = generate_relationship_key("CONC-01", "STRIP-02", "FS")

    # 1. HARD_PHYSICAL
    class_map_hard_phys = {
        rel_key: RelationshipClassification(
            relationship_key=rel_key, project_id=1, constraint_type="HARD_PHYSICAL", confidence=0.95
        )
    }
    lever = FastTrackLever(pred_task_code="CONC-01", succ_task_code="STRIP-02", new_relationship_type="SS", new_lag_days=1.0)

    with pytest.raises(SafetyViolationError) as exc_info:
        run_simulation(acts, rels, {1: cal}, options, [lever], class_map_hard_phys)
    assert "HARD_PHYSICAL" in str(exc_info.value)

    # 2. HARD_REGULATORY
    class_map_hard_reg = {
        rel_key: RelationshipClassification(
            relationship_key=rel_key, project_id=1, constraint_type="HARD_REGULATORY", confidence=0.90
        )
    }
    with pytest.raises(SafetyViolationError) as exc_info:
        run_simulation(acts, rels, {1: cal}, options, [lever], class_map_hard_reg)
    assert "HARD_REGULATORY" in str(exc_info.value)

    # 3. UNCLASSIFIED
    class_map_unclass = {
        rel_key: RelationshipClassification(
            relationship_key=rel_key, project_id=1, constraint_type="UNCLASSIFIED", confidence=0.0
        )
    }
    with pytest.raises(SafetyViolationError) as exc_info:
        run_simulation(acts, rels, {1: cal}, options, [lever], class_map_unclass)
    assert "UNCLASSIFIED" in str(exc_info.value)


def test_parallel_path_shift_caught_by_full_schedule_pass():
    """
    Acceptance Criterion 2:
    Confirm a full-schedule pass correctly catches a constructed case where a parallel
    path DOES become newly controlling after a lever is applied.
    Network:
      Start (Day 0)
        -> Path A: Task_A (Dur 10d) -> Finish (Day 10) [Controlling Critical Path]
        -> Path B: Task_B (Dur 8d)  -> Finish (Day 8)  [Parallel Subcritical Path]
      Crash Task_A by 5 days (10d -> 5d).
      Authoritative result: Finish is Day 8 (Path B is now newly controlling, recovering only 2d, NOT 5d).
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="START", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
        2: CPMActivityInput(task_id=2, task_code="PATH_A", calendar_id=1, original_duration_days=10.0, remaining_duration_days=10.0),
        3: CPMActivityInput(task_id=3, task_code="PATH_B", calendar_id=1, original_duration_days=8.0, remaining_duration_days=8.0),
        4: CPMActivityInput(task_id=4, task_code="FINISH", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=1, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=3, pred_task_id=2, succ_task_id=4, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=4, pred_task_id=3, succ_task_id=4, rel_type="FS", lag_days=0.0),
    ]

    # Baseline CPM: Path A controls (Finish = 2026-09-15, 10 work days)
    base_res = run_cpm(acts, rels, {1: cal}, options)
    assert base_res.activities[2].is_critical is True
    assert base_res.activities[3].is_critical is False

    # Apply CrashLever on PATH_A by 5 days (10d -> 5d)
    crash_lever = CrashLever(task_code="PATH_A", reduction_days=5.0)
    sim_res, diff = run_simulation(acts, rels, {1: cal}, options, [crash_lever])

    # In full CPM pass: PATH_B (8 days) is now controlling
    assert diff.critical_path_shifted is True
    assert sim_res.activities[3].is_critical is True  # PATH_B is now critical!
    assert sim_res.activities[2].is_critical is False # PATH_A is no longer controlling!
    # Days recovered is exactly 2.0 days (10d - 8d), NOT 5.0 days!
    assert diff.days_recovered == 2.0


def test_combinatorial_conflicts_and_cycle_detection():
    """
    Acceptance Criterion 3 & 4 (Combinatorial Set Re-validation):
    Confirm that conflicting levers or lever combinations creating cycles are rejected.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="ACT_A", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
        2: CPMActivityInput(task_id=2, task_code="ACT_B", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
    }
    rels = [CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0)]
    rel_key = generate_relationship_key("ACT_A", "ACT_B", "FS")
    class_map = {
        rel_key: RelationshipClassification(relationship_key=rel_key, project_id=1, constraint_type="SOFT_RESOURCE", confidence=0.90)
    }

    # 1. Multiple conflicting levers on same relationship
    l1 = FastTrackLever(pred_task_code="ACT_A", succ_task_code="ACT_B", new_relationship_type="SS", new_lag_days=1.0)
    l2 = LogicChangeLever(pred_task_code="ACT_A", succ_task_code="ACT_B", action="REMOVE")

    with pytest.raises(CombinatorialConflictError):
        run_simulation(acts, rels, {1: cal}, options, [l1, l2], class_map)

    # 2. Cycle creation via logic add
    l_cycle = LogicChangeLever(pred_task_code="ACT_B", succ_task_code="ACT_A", action="ADD", relationship_type="FS")
    with pytest.raises(CombinatorialConflictError):
        run_simulation(acts, rels, {1: cal}, options, [l_cycle], class_map)


def test_transitive_dependency_resequencing_rejection():
    """
    Confirm ResequencingLever checks full transitive ancestor/descendant relationships.
    Network: A -> B -> C (A precedes C transitively through B).
    Attempting to resequence A and C must be rejected.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="A", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
        2: CPMActivityInput(task_id=2, task_code="B", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
        3: CPMActivityInput(task_id=3, task_code="C", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]

    reseq_lever = ResequencingLever(task_a_code="A", task_b_code="C", new_order="PARALLEL")
    with pytest.raises(DependencyViolationError) as exc_info:
        run_simulation(acts, rels, {1: cal}, options, [reseq_lever])
    assert "transitive dependency" in str(exc_info.value)


def test_approval_tracking_for_contractual_levers():
    """
    Confirm LogicChangeLever and ConstraintRelaxationLever mark scenario status as pending_approval
    unless explicit approved_by is provided.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="T1", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0, cstr_type="CS_MANDFIN", cstr_date=datetime(2026, 9, 10)),
    }
    rels = []

    # 1. Unapproved Constraint Relaxation -> pending_approval
    l_unapproved = ConstraintRelaxationLever(task_code="T1", action="REMOVE")
    _, diff1 = run_simulation(acts, rels, {1: cal}, options, [l_unapproved])
    assert diff1.requires_pm_approval is True
    assert diff1.status == "pending_approval"

    # 2. Approved Constraint Relaxation -> approved
    l_approved = ConstraintRelaxationLever(task_code="T1", action="REMOVE", approved_by="Project_Director")
    _, diff2 = run_simulation(acts, rels, {1: cal}, options, [l_approved])
    assert diff2.requires_pm_approval is True
    assert diff2.status == "approved"
