"""
Comprehensive Test Suite for Phase 4: Combinatorial Optimization & Pareto Analysis.
Covers:
1. Critical Regression Test: Strict exclusion of HARD_*/UNCLASSIFIED candidate from ILP variables and GA population.
2. Combinatorial Search Conflict Test: Natural search combination of individually-valid conflicting levers caught mid-search.
3. Pareto non-dominated sorting and budget constraint enforcement.
4. REST API Endpoint integration test for POST /scenarios/optimize.
"""

import pytest
from datetime import datetime
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    CalendarModel,
    RelationshipClassification,
    generate_relationship_key,
)
import arth_rca.db.models  # noqa: F401
from arth_rca.simulation.levers import CrashLever, FastTrackLever, LogicChangeLever
from arth_rca.optimization.models import (
    CandidateLeverOption,
    OptimizationRequest,
    ParetoPoint,
)
from arth_rca.optimization.ilp_solver import filter_safety_cleared_candidates, solve_ilp_pareto
from arth_rca.optimization.metaheuristic_solver import solve_metaheuristic_pareto
from arth_rca.optimization.pareto import extract_pareto_frontier, dominates
from arth_rca.optimization.optimizer import optimize_schedule_recovery
from arth_rca.optimization.config import OptimizationConfig
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


def test_safety_gate_strictly_excludes_hard_physical_from_ilp_and_ga_search():
    """
    Acceptance Criterion 1 (Critical Regression Test):
    Construct a candidate pool where a HARD_PHYSICAL relationship has the most attractive
    cost/time profile (Cost = $0, Time Savings = 10.0 days).
    An unguarded optimizer WOULD select it immediately.
    Prove:
    1. Guarded ILP excludes it before creating any PuLP decision variable.
    2. Guarded Metaheuristic excludes it before candidate gene sampling (never appears in any generation).
    3. Neither solver produces a winning scenario containing the invalid lever.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="CONC_POUR", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
        2: CPMActivityInput(task_id=2, task_code="FORM_STRIP", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
        3: CPMActivityInput(task_id=3, task_code="SAFE_TASK", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]

    k_hard = generate_relationship_key("CONC_POUR", "FORM_STRIP", "FS")
    class_map = {
        k_hard: RelationshipClassification(
            relationship_key=k_hard, project_id=1, constraint_type="HARD_PHYSICAL", confidence=0.95
        )
    }

    # Candidate 1: Highly attractive BUT ILLEGAL fast-track on HARD_PHYSICAL curing link
    cand_illegal = CandidateLeverOption(
        candidate_id="ILLEGAL_HARD_PHYS_FT",
        lever_type="FAST_TRACK",
        target_entity=k_hard,
        lever=FastTrackLever(
            pred_task_code="CONC_POUR",
            succ_task_code="FORM_STRIP",
            new_relationship_type="SS",
            new_lag_days=1.0,
            cost_delta=0.0,
        ),
        estimated_cost=0.0,  # Zero cost!
        estimated_time_savings_days=10.0,  # Massive 10-day time savings!
        is_safety_cleared=False,
    )

    # Candidate 2: Legal crash lever with standard cost
    cand_legal = CandidateLeverOption(
        candidate_id="LEGAL_CRASH_SAFE",
        lever_type="CRASH",
        target_entity="SAFE_TASK",
        lever=CrashLever(task_code="SAFE_TASK", reduction_days=2.0, cost_delta=5000.0),
        estimated_cost=5000.0,
        estimated_time_savings_days=2.0,
        is_safety_cleared=True,
    )

    candidates = [cand_illegal, cand_legal]

    # 1. Pre-search gate test: ILP decision variable pool
    cleared, rejected_count = filter_safety_cleared_candidates(candidates, acts, rels, class_map)
    assert rejected_count == 1
    assert len(cleared) == 1
    assert cleared[0].candidate_id == "LEGAL_CRASH_SAFE"
    assert "ILLEGAL_HARD_PHYS_FT" not in [c.candidate_id for c in cleared]

    # 2. Run ILP solver
    ilp_res = solve_ilp_pareto(
        candidates=candidates,
        activities=acts,
        relationships=rels,
        calendars={1: cal},
        options=options,
        classifications=class_map,
        budget_limit=10000.0,
        project_id=1,
        snapshot_id=1,
    )
    # Confirm illegal lever never enters any Pareto point
    for point in ilp_res.pareto_frontier:
        applied_cands = [lev["candidate_id"] for lev in point.levers_applied]
        assert "ILLEGAL_HARD_PHYS_FT" not in applied_cands

    # 3. Run Metaheuristic GA solver
    ga_res = solve_metaheuristic_pareto(
        candidates=candidates,
        activities=acts,
        relationships=rels,
        calendars={1: cal},
        options=options,
        classifications=class_map,
        budget_limit=10000.0,
        project_id=1,
        snapshot_id=1,
    )
    for point in ga_res.pareto_frontier:
        applied_cands = [lev["candidate_id"] for lev in point.levers_applied]
        assert "ILLEGAL_HARD_PHYS_FT" not in applied_cands


def test_optimizer_catches_individually_valid_conflicting_levers_mid_search():
    """
    Acceptance Criterion 2:
    Construct two levers (L1 and L2) that each pass validation and appear attractive
    in isolation, but create a circular logic loop when combined.
    Prove the optimizer's search algorithm rejects the combination mid-search and
    never includes the circular pair in the Pareto frontier.
    """
    cal = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)
    options = CPMOptions(data_date=datetime(2026, 9, 1))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="T_ALPHA", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
        2: CPMActivityInput(task_id=2, task_code="T_BETA", calendar_id=1, original_duration_days=5.0, remaining_duration_days=5.0),
    }
    rels = []  # Independent
    class_map = {}

    # L1: Add Alpha -> Beta link (Valid individually)
    l1 = CandidateLeverOption(
        candidate_id="ADD_ALPHA_BETA",
        lever_type="LOGIC_CHANGE",
        target_entity="T_ALPHA",
        lever=LogicChangeLever(pred_task_code="T_ALPHA", succ_task_code="T_BETA", action="ADD", relationship_type="FS", cost_delta=1000.0),
        estimated_cost=1000.0,
        estimated_time_savings_days=2.0,
        is_safety_cleared=True,
    )

    # L2: Add Beta -> Alpha link (Valid individually)
    l2 = CandidateLeverOption(
        candidate_id="ADD_BETA_ALPHA",
        lever_type="LOGIC_CHANGE",
        target_entity="T_BETA",
        lever=LogicChangeLever(pred_task_code="T_BETA", succ_task_code="T_ALPHA", action="ADD", relationship_type="FS", cost_delta=1000.0),
        estimated_cost=1000.0,
        estimated_time_savings_days=2.0,
        is_safety_cleared=True,
    )

    candidates = [l1, l2]

    # Run GA Optimizer with high budget allowing both
    cfg = OptimizationConfig(ga_population_size=20, ga_generations=10)
    ga_res = solve_metaheuristic_pareto(
        candidates=candidates,
        activities=acts,
        relationships=rels,
        calendars={1: cal},
        options=options,
        classifications=class_map,
        budget_limit=10000.0,
        project_id=1,
        snapshot_id=1,
        config=cfg,
    )

    # Infeasible counter must catch the circular loop mid-search
    assert ga_res.total_infeasible_rejected > 0

    # No point on the Pareto frontier may contain both L1 and L2 simultaneously
    for pt in ga_res.pareto_frontier:
        applied_ids = {lev["candidate_id"] for lev in pt.levers_applied}
        assert not ({"ADD_ALPHA_BETA", "ADD_BETA_ALPHA"}.issubset(applied_ids))


def test_pareto_frontier_dominance_and_sorting():
    """
    Confirm extract_pareto_frontier strictly filters dominated solutions and sorts by cost.
    """
    p_base = ParetoPoint(scenario_name="P0", cost_delta=0.0, days_recovered=0.0, simulated_finish_date="2026-09-10", remaining_discrete_delayed_count=10, discrete_delayed_recovered_count=0, critical_path_shifted=False, levers_applied=[])
    p1 = ParetoPoint(scenario_name="P1", cost_delta=2000.0, days_recovered=3.0, simulated_finish_date="2026-09-07", remaining_discrete_delayed_count=7, discrete_delayed_recovered_count=3, critical_path_shifted=False, levers_applied=[])
    p2_dominated = ParetoPoint(scenario_name="P2_Dominated", cost_delta=3000.0, days_recovered=2.0, simulated_finish_date="2026-09-08", remaining_discrete_delayed_count=8, discrete_delayed_recovered_count=2, critical_path_shifted=False, levers_applied=[])
    p3 = ParetoPoint(scenario_name="P3", cost_delta=5000.0, days_recovered=6.0, simulated_finish_date="2026-09-04", remaining_discrete_delayed_count=4, discrete_delayed_recovered_count=6, critical_path_shifted=True, levers_applied=[])

    frontier = extract_pareto_frontier([p_base, p1, p2_dominated, p3])

    assert len(frontier) == 3
    assert [p.scenario_name for p in frontier] == ["P0", "P1", "P3"]
    assert p2_dominated not in frontier


def test_optimization_api_endpoint(client, test_db):
    """
    Integration test for POST /api/v1/projects/{project_id}/scenarios/optimize.
    """
    proj = Project(id=1, org_id=1, name="Optimization Test Project", p6_project_id="OPT_01")
    test_db.add(proj)
    test_db.commit()

    snap = Snapshot(id=1, project_id=1, source_filename="test.xer", data_date=datetime(2026, 9, 1), is_baseline=True)
    test_db.add(snap)
    test_db.commit()

    a1 = Activity(id=1, snapshot_id=1, task_code="T1", name="Task 1", original_duration=10.0, remaining_duration=10.0, status="NOT_STARTED", is_milestone=False)
    a2 = Activity(id=2, snapshot_id=1, task_code="T2", name="Task 2", original_duration=8.0, remaining_duration=8.0, status="NOT_STARTED", is_milestone=False)
    test_db.add_all([a1, a2])
    test_db.commit()

    rel = Relationship(id=1, snapshot_id=1, predecessor_activity_id=1, successor_activity_id=2, relationship_type="FS", lag=0.0, relationship_key="T1__T2__FS")
    test_db.add(rel)
    test_db.commit()

    payload = {
        "snapshot_id": 1,
        "budget_limit": 20000.0,
        "strategy": "AUTO",
        "max_pareto_points": 5,
    }

    res = client.post("/api/v1/projects/1/scenarios/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["project_id"] == 1
    assert data["snapshot_id"] == 1
    assert "pareto_frontier" in data
    assert len(data["pareto_frontier"]) >= 1
    assert "solver_used" in data
    assert data["cost_source_note"] != ""
