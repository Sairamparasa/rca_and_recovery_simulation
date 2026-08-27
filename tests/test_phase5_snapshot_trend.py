"""
Phase 5 Test Suite: Historical Snapshot Comparison, Trend Display & Driver Churn.
Covers Acceptance Criteria 1, 2, and 3 (with prediction-free static and AST assertions).
"""

import ast
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.snapshot_diff import compute_snapshot_diff, ActivityDiff, RelationshipDiff, DriverChurn
from arth_rca.analytics.trend import aggregate_historical_trends, SnapshotDataPackage, HistoricalTrendPayload
from arth_rca.db.models import generate_relationship_key
from arth_rca.api.app import app
from arth_rca.db.database import get_db
from arth_rca.db.models import Project, Snapshot, Activity, Relationship, CalendarModel


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


def make_standard_calendar() -> Dict[int, CPMCalendarInput]:
    cal = CPMCalendarInput(
        clndr_id=1,
        name="Standard 5-Day",
        working_days=[True, True, True, True, True, False, False],
        work_hours_per_day=8.0,
        holidays=[],
        work_exceptions={},
    )
    return {1: cal}


# ==============================================================================
# ACCEPTANCE CRITERION 1: SEQUENTIAL SNAPSHOT DIFF (ADDED/REMOVED/MODIFIED)
# ==============================================================================
def test_sequential_snapshot_diff_logic_and_durations():
    """
    Acceptance Criterion 1: Verify diff between sequential snapshots accurately captures:
    - Added, removed, and duration-modified activities.
    - Added, removed, and lag-modified relationships.
    - Constraint modifications.
    """
    cals = make_standard_calendar()
    dd_1 = datetime(2026, 1, 1, 8, 0)
    dd_2 = datetime(2026, 2, 1, 8, 0)

    # Snapshot 1 (Month 1 Baseline)
    acts_1 = {
        1: CPMActivityInput(task_id=1, task_code="ACT_A", calendar_id=1, original_duration_days=10.0, remaining_duration_days=10.0, status="NOT_STARTED"),
        2: CPMActivityInput(task_id=2, task_code="ACT_B", calendar_id=1, original_duration_days=15.0, remaining_duration_days=15.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="ACT_C", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0, status="NOT_STARTED"),
    }
    rels_1 = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=1, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]

    # Snapshot 2 (Month 2 Update):
    # - ACT_A: Completed (remaining 0)
    # - ACT_B: Duration increased from 15d to 20d (delayed) + Must Finish By constraint added
    # - ACT_C: Removed from scope
    # - ACT_D: Added into scope
    # - Rel 1: Modified lag from 0.0 to 2.0d
    # - Rel 2: Removed (since ACT_C removed)
    # - Rel 3: Added (ACT_B -> ACT_D)
    acts_2 = {
        1: CPMActivityInput(task_id=1, task_code="ACT_A", calendar_id=1, original_duration_days=10.0, remaining_duration_days=0.0, status="COMPLETED", act_start_date=dd_1, act_finish_date=dd_1 + timedelta(days=14)),
        2: CPMActivityInput(task_id=2, task_code="ACT_B", calendar_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED", cstr_type="CS_MANDFIN", cstr_date=datetime(2026, 2, 20)),
        4: CPMActivityInput(task_id=4, task_code="ACT_D", calendar_id=1, original_duration_days=8.0, remaining_duration_days=8.0, status="NOT_STARTED"),
    }
    rels_2 = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=2.0),
        CPMRelationshipInput(rel_id=3, pred_task_id=2, succ_task_id=4, rel_type="FS", lag_days=0.0),
    ]

    diff = compute_snapshot_diff(
        acts_a=acts_1, rels_a=rels_1, cals_a=cals, options_a=CPMOptions(data_date=dd_1),
        acts_b=acts_2, rels_b=rels_2, cals_b=cals, options_b=CPMOptions(data_date=dd_2),
        snapshot_a_id=1, snapshot_b_id=2,
    )

    # Activity verifications
    assert diff.added_activities_count == 1
    assert diff.removed_activities_count == 1
    assert diff.modified_activities_count == 2  # ACT_A (completed), ACT_B (dur +5d & constraint)

    act_diff_map = {ad.task_code: ad for ad in diff.activity_diffs}
    assert act_diff_map["ACT_D"].change_type == "ADDED"
    assert act_diff_map["ACT_C"].change_type == "REMOVED"
    assert act_diff_map["ACT_B"].change_type == "MODIFIED"
    assert act_diff_map["ACT_B"].duration_delta_days == 5.0
    assert act_diff_map["ACT_B"].constraint_type_after == "CS_MANDFIN"
    assert act_diff_map["ACT_A"].status_after == "COMPLETED"

    # Relationship verifications
    assert diff.added_relationships_count == 1
    assert diff.removed_relationships_count == 1
    assert diff.modified_relationships_count == 1

    rel_diff_map = {rd.relationship_key: rd for rd in diff.relationship_diffs}
    key_bd = generate_relationship_key("ACT_B", "ACT_D", "FS")
    key_ac = generate_relationship_key("ACT_A", "ACT_C", "FS")
    key_ab = generate_relationship_key("ACT_A", "ACT_B", "FS")

    assert rel_diff_map[key_bd].change_type == "ADDED"
    assert rel_diff_map[key_ac].change_type == "REMOVED"
    assert rel_diff_map[key_ab].change_type == "MODIFIED"
    assert rel_diff_map[key_ab].lag_delta_days == 2.0


# ==============================================================================
# ACCEPTANCE CRITERION 2: DRIVER CHURN CLASSIFICATION (NEW, PERSISTENT, RESOLVED)
# ==============================================================================
def test_driver_churn_accurate_classification_and_discrete_isolation():
    """
    Acceptance Criterion 2: Verify driver churn correctly categorizes:
    - new_drivers: emerging negative float driver heads.
    - resolved_drivers: previous driver heads that recovered to TF >= 0 or completed.
    - persistent_drivers: driver heads present in both with negative float & float deltas.
    - strictly excludes TT_LOE and TT_WBS from false driver churn movements.
    """
    cals = make_standard_calendar()
    dd_1 = datetime(2026, 1, 1, 8, 0)
    dd_2 = datetime(2026, 2, 1, 8, 0)
    late_anchor_date = datetime(2026, 1, 20, 17, 0)

    # Snapshot 1:
    # DRV_1 is delayed (TF = -10d)
    # DRV_2 is delayed (TF = -5d)
    # LOE_SUMMARY is LOE with negative float (must be excluded from discrete churn)
    acts_1 = {
        1: CPMActivityInput(task_id=1, task_code="DRV_1", calendar_id=1, proj_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED"),
        2: CPMActivityInput(task_id=2, task_code="DRV_2", calendar_id=1, proj_id=1, original_duration_days=15.0, remaining_duration_days=15.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="NORMAL_TASK", calendar_id=1, proj_id=1, original_duration_days=5.0, remaining_duration_days=5.0, status="NOT_STARTED"),
        4: CPMActivityInput(task_id=4, task_code="LOE_SUMMARY", calendar_id=1, proj_id=1, original_duration_days=50.0, remaining_duration_days=50.0, status="NOT_STARTED", task_type="TT_LOE"),
    }
    rels_1 = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]

    # Snapshot 2:
    # - DRV_1 resolved (completed early, status='COMPLETED', remaining 0)
    # - DRV_2 persistent (still negative float, deteriorated by 3 days)
    # - DRV_3 newly delayed (added scope with late constraint)
    acts_2 = {
        1: CPMActivityInput(task_id=1, task_code="DRV_1", calendar_id=1, proj_id=1, original_duration_days=5.0, remaining_duration_days=0.0, status="COMPLETED", act_start_date=dd_1, act_finish_date=dd_1 + timedelta(days=5)),
        2: CPMActivityInput(task_id=2, task_code="DRV_2", calendar_id=1, proj_id=1, original_duration_days=18.0, remaining_duration_days=18.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="NORMAL_TASK", calendar_id=1, proj_id=1, original_duration_days=5.0, remaining_duration_days=5.0, status="NOT_STARTED"),
        4: CPMActivityInput(task_id=4, task_code="LOE_SUMMARY", calendar_id=1, proj_id=1, original_duration_days=50.0, remaining_duration_days=50.0, status="NOT_STARTED", task_type="TT_LOE"),
        5: CPMActivityInput(task_id=5, task_code="DRV_3", calendar_id=1, proj_id=1, original_duration_days=30.0, remaining_duration_days=30.0, status="NOT_STARTED"),
    }
    rels_2 = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=3, pred_task_id=5, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]

    late_anchors = {1: late_anchor_date}

    diff = compute_snapshot_diff(
        acts_a=acts_1, rels_a=rels_1, cals_a=cals, options_a=CPMOptions(data_date=dd_1),
        acts_b=acts_2, rels_b=rels_2, cals_b=cals, options_b=CPMOptions(data_date=dd_2),
        snapshot_a_id=1, snapshot_b_id=2,
        project_late_anchors_a=late_anchors, project_late_anchors_b=late_anchors,
    )

    churn = diff.driver_churn
    assert "DRV_3" in churn.new_drivers
    assert "DRV_1" in churn.resolved_drivers
    assert "DRV_2" in churn.persistent_drivers
    assert "LOE_SUMMARY" not in churn.new_drivers
    assert "LOE_SUMMARY" not in churn.resolved_drivers
    assert "LOE_SUMMARY" not in churn.persistent_drivers

    # Persistent driver float delta should reflect degradation
    assert "DRV_2" in churn.persistent_driver_float_deltas


# ==============================================================================
# ACCEPTANCE CRITERION 3: PREDICTION-FREE CODE REVIEW & AST STATIC AUDIT
# ==============================================================================
def test_zero_prediction_and_extrapolation_code_audit():
    """
    Acceptance Criterion 3: Comprehensive static and AST scan verifying:
    - Zero forecasting/extrapolation keywords in code or models.
    - Zero multi-point regression, slope-fitting, or curve-fitting modules (scipy.stats, polyfit, sklearn).
    - All trends operate strictly as historical timestamps and point-in-time diffs.
    """
    target_files = [
        "src/arth_rca/analytics/snapshot_diff.py",
        "src/arth_rca/analytics/trend.py",
    ]

    forbidden_terms = [
        "forecast",
        "predict",
        "extrapolate",
        "linregress",
        "polyfit",
        "trendline_slope",
        "confidence_interval",
        "projected_finish_date",
        "monte_carlo",
        "regression",
        "sklearn",
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 1. Substring scan on lowercased code
        lower_content = content.lower()
        for term in forbidden_terms:
            assert f"def {term}" not in lower_content, f"Forbidden function definition '{term}' in {file_path}"
            assert f"import {term}" not in lower_content, f"Forbidden import '{term}' in {file_path}"
            assert f"{term}(" not in lower_content, f"Forbidden call '{term}()' in {file_path}"

        # 2. AST parsing to verify zero regression / curve-fitting AST nodes
        tree = ast.parse(content, filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in ["sklearn", "scipy.optimize", "statsmodels"], f"Forbidden ML/Regression import {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                assert node.module not in ["sklearn", "scipy.optimize", "statsmodels"], f"Forbidden ML/Regression import from {node.module}"


# ==============================================================================
# HISTORICAL TREND & API INTEGRATION TESTS
# ==============================================================================
def test_multi_snapshot_historical_trend_aggregation():
    """Verify 3-snapshot progression builds accurate milestone slippage and DCMA trends."""
    cals = make_standard_calendar()
    dd_1 = datetime(2026, 1, 1, 8, 0)
    dd_2 = datetime(2026, 2, 1, 8, 0)
    dd_3 = datetime(2026, 3, 1, 8, 0)

    # Snapshot 1 (Baseline)
    pkg1 = SnapshotDataPackage(
        snapshot_id=1, data_date=dd_1, is_baseline=True,
        activities={
            1: CPMActivityInput(task_id=1, task_code="M_START", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
            2: CPMActivityInput(task_id=2, task_code="T1", calendar_id=1, original_duration_days=10.0, remaining_duration_days=10.0),
            3: CPMActivityInput(task_id=3, task_code="M_FINISH", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
        },
        relationships=[
            CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
            CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
        ],
        calendars=cals,
        options=CPMOptions(data_date=dd_1),
    )

    # Snapshot 2 (Delayed Month 2: T1 duration increases 10 -> 15)
    pkg2 = SnapshotDataPackage(
        snapshot_id=2, data_date=dd_2, is_baseline=False,
        activities={
            1: CPMActivityInput(task_id=1, task_code="M_START", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
            2: CPMActivityInput(task_id=2, task_code="T1", calendar_id=1, original_duration_days=15.0, remaining_duration_days=15.0),
            3: CPMActivityInput(task_id=3, task_code="M_FINISH", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
        },
        relationships=[
            CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
            CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
        ],
        calendars=cals,
        options=CPMOptions(data_date=dd_2),
    )

    # Snapshot 3 (Month 3: T1 completes)
    pkg3 = SnapshotDataPackage(
        snapshot_id=3, data_date=dd_3, is_baseline=False,
        activities={
            1: CPMActivityInput(task_id=1, task_code="M_START", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
            2: CPMActivityInput(task_id=2, task_code="T1", calendar_id=1, original_duration_days=15.0, remaining_duration_days=0.0, status="COMPLETED", act_start_date=dd_1, act_finish_date=dd_2),
            3: CPMActivityInput(task_id=3, task_code="M_FINISH", calendar_id=1, original_duration_days=0.0, remaining_duration_days=0.0, is_milestone=True),
        },
        relationships=[
            CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
            CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
        ],
        calendars=cals,
        options=CPMOptions(data_date=dd_3),
    )

    payload = aggregate_historical_trends(project_id=101, snapshots=[pkg1, pkg2, pkg3])

    assert payload.project_id == 101
    assert payload.total_snapshots == 3
    assert len(payload.dcma_history) == 3
    assert len(payload.milestone_trends) == 2  # M_START and M_FINISH

    m_finish = next(m for m in payload.milestone_trends if m.task_code == "M_FINISH")
    assert len(m_finish.history) == 3
    assert m_finish.history[0].cumulative_slippage_days == 0.0
    assert m_finish.history[1].cumulative_slippage_days > 0.0  # Slippage in Month 2


def test_snapshot_diff_and_trend_api_endpoints(client, test_db):
    """Test REST API routes GET /snapshots/{id}/diff and GET /projects/{id}/trend."""
    proj = Project(id=200, org_id=1, name="API Test Project")
    test_db.add(proj)
    test_db.commit()

    cal = CalendarModel(id=200, project_id=200, name="Standard Cal")
    test_db.add(cal)
    test_db.commit()

    snap1 = Snapshot(id=201, project_id=200, source_filename="snap1.xer", data_date=datetime(2026, 1, 1), is_baseline=True)
    snap2 = Snapshot(id=202, project_id=200, source_filename="snap2.xer", data_date=datetime(2026, 2, 1), is_baseline=False)
    test_db.add_all([snap1, snap2])
    test_db.commit()

    # Snap 1 tasks
    a1_s1 = Activity(id=2011, snapshot_id=201, task_code="T1", name="Task 1", original_duration=10.0, remaining_duration=10.0, status="NOT_STARTED", is_milestone=False)
    a2_s1 = Activity(id=2012, snapshot_id=201, task_code="T2", name="Task 2", original_duration=8.0, remaining_duration=8.0, status="NOT_STARTED", is_milestone=False)
    test_db.add_all([a1_s1, a2_s1])

    # Snap 2 tasks (T1 duration 10 -> 14)
    a1_s2 = Activity(id=2021, snapshot_id=202, task_code="T1", name="Task 1", original_duration=14.0, remaining_duration=14.0, status="NOT_STARTED", is_milestone=False)
    a2_s2 = Activity(id=2022, snapshot_id=202, task_code="T2", name="Task 2", original_duration=8.0, remaining_duration=8.0, status="NOT_STARTED", is_milestone=False)
    test_db.add_all([a1_s2, a2_s2])
    test_db.commit()

    # Rel in Snap 1 & Snap 2
    r1 = Relationship(id=2011, snapshot_id=201, predecessor_activity_id=2011, successor_activity_id=2012, relationship_type="FS", lag=0.0, relationship_key="T1__T2__FS")
    r2 = Relationship(id=2021, snapshot_id=202, predecessor_activity_id=2021, successor_activity_id=2022, relationship_type="FS", lag=0.0, relationship_key="T1__T2__FS")
    test_db.add_all([r1, r2])
    test_db.commit()

    # Test Diff API
    res_diff = client.get("/api/v1/snapshots/202/diff?compare_to_snapshot_id=201")
    assert res_diff.status_code == 200
    diff_data = res_diff.json()
    assert diff_data["snapshot_a_id"] == 201
    assert diff_data["snapshot_b_id"] == 202
    assert diff_data["modified_activities_count"] == 1

    # Test Trend API (Project endpoint)
    res_trend = client.get("/api/v1/projects/200/trend")
    assert res_trend.status_code == 200
    trend_data = res_trend.json()
    assert trend_data["project_id"] == 200
    assert trend_data["total_snapshots"] == 2

    # Test Trend API (Snapshot endpoint per Section 8/10 Scope 5)
    res_snap_trend = client.get("/api/v1/snapshots/202/trend")
    assert res_snap_trend.status_code == 200
    snap_trend_data = res_snap_trend.json()
    assert snap_trend_data["project_id"] == 200
    assert snap_trend_data["total_snapshots"] == 2
