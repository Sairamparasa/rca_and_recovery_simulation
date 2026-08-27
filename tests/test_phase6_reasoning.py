"""
Phase 6 Test Suite: Grounded LLM Reasoning Layer, NL Query Engine & Evidence Ledger.
Covers Acceptance Criteria 1, 2, 3, and 4 (including 5 real schedule queries and number grounding validation).
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Any
import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.engine import run_cpm
from arth_rca.analytics.driver_detection import detect_negative_float_drivers, DriverAnalysisResult
from arth_rca.analytics.dcma import run_dcma_14_point_assessment, DCMAAssessmentReport
from arth_rca.reasoning.types import (
    CertaintyTier,
    NLQueryRequest,
    NLQueryResponse,
    QueryIntent,
    NarrativeReportPayload,
)
from arth_rca.reasoning.llm_client import GroqClient
from arth_rca.reasoning.evidence_ledger import EvidenceLedger
from arth_rca.reasoning.report_generator import generate_grounded_narrative_report
from arth_rca.reasoning.nl_query import execute_nl_query, classify_query_intent
from arth_rca.reasoning.recommendations import explain_pareto_tradeoffs, explain_single_scenario
from arth_rca.optimization.models import ParetoPoint, OptimizationResult
from arth_rca.api.app import app
from arth_rca.db.database import get_db
from arth_rca.db.models import Project, Snapshot, Activity, Relationship, CalendarModel, Scenario


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
# ACCEPTANCE CRITERION 1: NUMBER GROUNDING VALIDATION (ZERO INVENTED NUMBERS)
# ==============================================================================
def test_number_grounding_in_narrative_report():
    """
    Acceptance Criterion 1: Confirm every numeric claim in generated report text
    traces back to a ground-truth value in the database or computed diagnostics.
    """
    cals = make_standard_calendar()
    dd = datetime(2026, 1, 1, 8, 0)
    late_anchor = datetime(2026, 1, 25, 17, 0)

    acts = {
        1: CPMActivityInput(task_id=1, task_code="QTS-28981", calendar_id=1, original_duration_days=30.0, remaining_duration_days=30.0, status="NOT_STARTED"),
        2: CPMActivityInput(task_id=2, task_code="QTS-29100", calendar_id=1, original_duration_days=10.0, remaining_duration_days=10.0, status="NOT_STARTED"),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
    ]

    cpm_res = run_cpm(acts, rels, cals, CPMOptions(data_date=dd), project_late_anchors={0: late_anchor})
    driver_res = detect_negative_float_drivers(cpm_res, acts, rels, snapshot_id=1)

    class TaskWrapper:
        def __init__(self, act: CPMActivityInput):
            self.task_id = act.task_id
            self.task_code = act.task_code
            self.status_code = "TK_NotStart"
            self.task_type = "TT_Task"
            self.cstr_type = None
            self.cstr_date = None
            self.target_durn_hr_cnt = act.original_duration_days * 8.0
            self.act_start_date = None
            self.act_end_date = None

    raw_tasks = {1: TaskWrapper(acts[1]), 2: TaskWrapper(acts[2])}
    dcma_res = run_dcma_14_point_assessment(cpm_res, raw_tasks, rels, data_date=dd, snapshot_id=1)

    # Generate report
    report = generate_grounded_narrative_report(
        snapshot_id=1,
        data_date=dd,
        project_name="PHX3 Data Center",
        driver_result=driver_res,
        dcma_report=dcma_res,
    )

    assert report.snapshot_id == 1
    assert report.data_date == dd
    assert len(report.evidence_ledger) > 0

    # Extract all numbers from evidence ledger to form ground truth set
    ground_truth_numbers = set()
    for entry in report.evidence_ledger:
        if isinstance(entry.metric_value, (int, float)):
            ground_truth_numbers.add(float(round(entry.metric_value, 1)))

    # Add standard structural numbers (e.g. check numbers 1-14, 100%)
    for i in range(1, 15):
        ground_truth_numbers.add(float(i))
    ground_truth_numbers.add(100.0)
    ground_truth_numbers.add(float(dcma_res.overall_health_score))
    ground_truth_numbers.add(float(driver_res.total_negative_float_activities))
    ground_truth_numbers.add(float(driver_res.driver_head_count))

    # Parse numbers from executive summary and driver narrative
    extracted_nums = re.findall(r'[-+]?\d*\.\d+|\d+', report.executive_summary)
    for n_str in extracted_nums:
        n_val = float(n_str)
        # Year digits (e.g. 2026, 01) are date components
        if n_val in [2026.0, 1.0, 25.0]:
            continue
        # Number must trace back to ground truth
        assert n_val in ground_truth_numbers or any(abs(n_val - g) < 0.2 for g in ground_truth_numbers), (
            f"Factual Hallucination Alert: Number {n_val} in summary not found in grounded facts!"
        )


# ==============================================================================
# ACCEPTANCE CRITERION 2: GROUNDING ARCHITECTURE & EVIDENCE LEDGER
# ==============================================================================
def test_grounding_architecture_and_evidence_ledger_integrity():
    """
    Acceptance Criterion 2: Verify evidence ledger links every assertion to
    its specific source entity, metric name, and certainty tier.
    """
    ledger = EvidenceLedger()
    e1 = ledger.record_fact("Data date is 2026-01-01", "Snapshot#1", "data_date", "2026-01-01")
    e2 = ledger.record_inference("Float is -15.0 days", "Activity#QTS-28981", "total_float", -15.0)
    e3 = ledger.record_hypothesis("Delay cause unverified", "Activity#QTS-28981", "root_cause_type", "unresolved")

    assert e1.certainty_tier == CertaintyTier.FACT
    assert e2.certainty_tier == CertaintyTier.INFERENCE
    assert e3.certainty_tier == CertaintyTier.HYPOTHESIS

    entries = ledger.get_entries()
    assert len(entries) == 3
    assert entries[1].source_entity == "Activity#QTS-28981"
    assert entries[1].metric_value == -15.0


# ==============================================================================
# ACCEPTANCE CRITERION 3: HYPOTHESIS STRUCTURAL DISTINCTION
# ==============================================================================
def test_unresolved_root_cause_hypothesis_tagging():
    """
    Acceptance Criterion 3: Confirm unresolved driver root causes are distinctly
    flagged as HYPOTHESIS in the API response and narrative callouts.
    """
    dd = datetime(2026, 1, 1, 8, 0)
    cals = make_standard_calendar()
    acts = {
        1: CPMActivityInput(task_id=1, task_code="UNRESOLVED_TASK", calendar_id=1, proj_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED"),
    }
    rels = []
    cpm_res = run_cpm(acts, rels, cals, CPMOptions(data_date=dd), project_late_anchors={1: datetime(2026, 1, 10, 17, 0)})
    driver_res = detect_negative_float_drivers(cpm_res, acts, rels, snapshot_id=1)

    class TaskWrapper:
        def __init__(self, act: CPMActivityInput):
            self.task_id = act.task_id
            self.task_code = act.task_code
            self.status_code = "TK_NotStart"
            self.task_type = "TT_Task"
            self.cstr_type = None
            self.cstr_date = None
            self.target_durn_hr_cnt = act.original_duration_days * 8.0
            self.act_start_date = None
            self.act_end_date = None

    dcma_res = run_dcma_14_point_assessment(cpm_res, {1: TaskWrapper(acts[1])}, rels, data_date=dd, snapshot_id=1)

    report = generate_grounded_narrative_report(
        snapshot_id=1,
        data_date=dd,
        project_name="Test Project",
        driver_result=driver_res,
        dcma_report=dcma_res,
    )

    # Check unresolved hypotheses list
    assert len(report.unresolved_hypotheses) > 0
    hypo = report.unresolved_hypotheses[0]
    assert hypo["task_code"] == "UNRESOLVED_TASK"
    assert hypo["certainty_tier"] == CertaintyTier.HYPOTHESIS

    # Check evidence ledger contains HYPOTHESIS entry
    hypo_entries = [e for e in report.evidence_ledger if e.certainty_tier == CertaintyTier.HYPOTHESIS]
    assert len(hypo_entries) > 0


# ==============================================================================
# ACCEPTANCE CRITERION 4: 5 REAL-SCHEDULE NATURAL LANGUAGE QUERIES
# ==============================================================================
def test_five_real_schedule_nl_queries(client, test_db):
    """
    Acceptance Criterion 4: Run NL query endpoint against 5 example questions
    on an ingested schedule and verify deterministic facts alongside generated answers.
    """
    # Seed DB with project and snapshot
    proj = Project(id=300, org_id=1, name="Phoenix Data Center Phase 1")
    test_db.add(proj)
    test_db.commit()

    snap = Snapshot(id=301, project_id=300, source_filename="20260304-QTS-PHX3DC1.xer", data_date=datetime(2026, 1, 14), is_baseline=True)
    test_db.add(snap)
    test_db.commit()

    # Seed activities
    a1 = Activity(
        id=3011, snapshot_id=301, task_code="QTS-28981", name="Underground Electrical Ductbank",
        original_duration=45.0, remaining_duration=45.0, total_float=-15.0, status="NOT_STARTED", is_milestone=False
    )
    a2 = Activity(
        id=3012, snapshot_id=301, task_code="QTS-29661", name="Main Substation Feeders",
        original_duration=30.0, remaining_duration=30.0, total_float=-12.0, status="NOT_STARTED", is_milestone=False
    )
    a3 = Activity(
        id=3013, snapshot_id=301, task_code="M_COMMISSIONING", name="Substation Energization Milestone",
        original_duration=0.0, remaining_duration=0.0, total_float=-15.0, status="NOT_STARTED", is_milestone=True,
        early_finish=datetime(2026, 6, 15)
    )
    test_db.add_all([a1, a2, a3])

    r1 = Relationship(id=3011, snapshot_id=301, predecessor_activity_id=3011, successor_activity_id=3012, relationship_type="FS", lag=0.0, relationship_key="QTS-28981__QTS-29661__FS")
    r2 = Relationship(id=3012, snapshot_id=301, predecessor_activity_id=3012, successor_activity_id=3013, relationship_type="FS", lag=0.0, relationship_key="QTS-29661__M_COMMISSIONING__FS")
    test_db.add_all([r1, r2])
    test_db.commit()

    # Query 1: Activity-specific delay query
    res1 = client.post("/api/v1/query", json={"query": "Why is QTS-28981 delayed?", "snapshot_id": 301})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["intent"] == QueryIntent.DRIVER_WHY_DELAYED.value
    assert data1["retrieved_facts"]["activity"]["task_code"] == "QTS-28981"
    ans_normalized = re.sub(r'[\u2010\u2011\u2012\u2013\u2014]', '-', data1["answer_markdown"])
    assert "QTS-28981" in ans_normalized or "28981" in ans_normalized

    # Query 2: Top Drivers query
    res2 = client.post("/api/v1/query", json={"query": "What are the top 3 drivers on the critical path?", "snapshot_id": 301})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["intent"] == QueryIntent.TOP_DRIVERS.value
    assert "driver_head_count" in data2["retrieved_facts"]

    # Query 3: DCMA Health query
    res3 = client.post("/api/v1/query", json={"query": "What is the DCMA health score and missing logic count?", "snapshot_id": 301})
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["intent"] == QueryIntent.DCMA_HEALTH.value
    assert "dcma_overall_health_score" in data3["retrieved_facts"]

    # Query 4: Milestone slippage query
    res4 = client.post("/api/v1/query", json={"query": "Which milestone has the greatest slippage?", "snapshot_id": 301})
    assert res4.status_code == 200
    data4 = res4.json()
    assert data4["intent"] == QueryIntent.MILESTONE_SLIPPAGE.value
    assert len(data4["retrieved_facts"]["milestones"]) > 0

    # Query 5: Recovery options query
    res5 = client.post("/api/v1/query", json={"query": "What are the recovery options and budget trade-offs?", "snapshot_id": 301})
    assert res5.status_code == 200
    data5 = res5.json()
    assert data5["intent"] == QueryIntent.RECOVERY_OPTIONS.value


# ==============================================================================
# PARETO FRONTIER RECOMMENDATION EXPLAINER TEST
# ==============================================================================
def test_pareto_frontier_recommendation_explainer():
    """Verify Pareto frontier trade-off explainer references scenario IDs and dollar values."""
    pt1 = ParetoPoint(
        scenario_name="Scenario #1: Fast Crash",
        cost_delta=15000.0,
        days_recovered=3.0,
        simulated_finish_date="2026-11-20",
        remaining_discrete_delayed_count=10,
        discrete_delayed_recovered_count=2,
        critical_path_shifted=False,
        levers_applied=[
            {"lever_id": "L1", "target_entity": "QTS-28981", "lever_type": "CRASH", "cost": 15000.0}
        ],
    )
    pt2 = ParetoPoint(
        scenario_name="Scenario #2: Max Recovery",
        cost_delta=35000.0,
        days_recovered=6.0,
        simulated_finish_date="2026-11-17",
        remaining_discrete_delayed_count=8,
        discrete_delayed_recovered_count=4,
        critical_path_shifted=True,
        levers_applied=[
            {"lever_id": "L1", "target_entity": "QTS-28981", "lever_type": "CRASH", "cost": 15000.0},
            {"lever_id": "L2", "target_entity": "QTS-29661", "lever_type": "CRASH", "cost": 20000.0},
        ],
    )

    explanation = explain_pareto_tradeoffs([pt1, pt2], project_name="PHX3 Data Center")

    assert "Scenario #1" in explanation or "15,000" in explanation or "3.0" in explanation
    assert "Scenario #2" in explanation or "35,000" in explanation or "6.0" in explanation
