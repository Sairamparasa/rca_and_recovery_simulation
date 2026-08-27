"""
Exact Integer Linear Programming (ILP) Solver using PuLP for bounded candidate spaces.
Solves the discrete Time-Cost Trade-off Problem with strict pre-search safety gates.
"""

from typing import List, Dict, Tuple, Optional, Any, Set
import time
import pulp
import networkx as nx

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.classification import is_fasttrack_candidate
from arth_rca.db.models import generate_relationship_key, RelationshipClassification
from arth_rca.simulation.levers import (
    AnyLever,
    CrashLever,
    FastTrackLever,
    LogicChangeLever,
    ResequencingLever,
    validate_transitive_independence,
)
from arth_rca.simulation.engine import run_simulation, validate_lever_set, build_dependency_dag
from arth_rca.optimization.models import CandidateLeverOption, ParetoPoint, OptimizationResult
from arth_rca.optimization.pareto import extract_pareto_frontier


def filter_safety_cleared_candidates(
    candidates: List[CandidateLeverOption],
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    classifications: Dict[str, RelationshipClassification],
) -> Tuple[List[CandidateLeverOption], int]:
    """
    Strict Programmatic Pre-Search Gate:
    Filters the candidate pool so that unsafe levers (HARD_PHYSICAL, HARD_REGULATORY,
    HARD_SAFETY, UNCLASSIFIED fast-tracks, or transitive dependency violations)
    NEVER enter the ILP decision variable pool.
    Returns: (cleared_candidates, rejected_count)
    """
    task_code_to_id = {act.task_code: tid for tid, act in activities.items()}
    graph = build_dependency_dag(activities, relationships)

    cleared: List[CandidateLeverOption] = []
    rejected_count = 0

    for cand in candidates:
        lever = cand.lever
        is_safe = True

        if isinstance(lever, FastTrackLever):
            rel_key = generate_relationship_key(lever.pred_task_code, lever.succ_task_code, "FS")
            rel_class = classifications.get(rel_key)
            if not is_fasttrack_candidate(rel_class):
                is_safe = False

        elif isinstance(lever, ResequencingLever):
            tid_a = task_code_to_id.get(lever.task_a_code)
            tid_b = task_code_to_id.get(lever.task_b_code)
            if tid_a is None or tid_b is None or not validate_transitive_independence(graph, tid_a, tid_b):
                is_safe = False

        if is_safe:
            cleared.append(cand)
        else:
            rejected_count += 1

    return cleared, rejected_count


def solve_ilp_pareto(
    candidates: List[CandidateLeverOption],
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
    classifications: Dict[str, RelationshipClassification],
    budget_limit: float,
    project_id: int,
    snapshot_id: int,
    project_data_dates: Optional[Dict[int, Any]] = None,
    project_late_anchors: Optional[Dict[int, Any]] = None,
    budget_steps: int = 10,
) -> OptimizationResult:
    """
    Solve exact Time-Cost Trade-Off Pareto frontier using PuLP ILP sweep across budget tiers.
    """
    start_time = time.time()

    # 1. Strict pre-search gate
    cleared_candidates, initial_rejected = filter_safety_cleared_candidates(
        candidates, activities, relationships, classifications
    )

    evaluated_points: List[ParetoPoint] = []
    infeasible_count = initial_rejected

    # 2. Baseline point (Cost = 0)
    sim_base, diff_base = run_simulation(
        activities, relationships, calendars, options, [], classifications,
        project_data_dates=project_data_dates, project_late_anchors=project_late_anchors,
        scenario_name="Baseline",
    )
    evaluated_points.append(
        ParetoPoint(
            scenario_name="Baseline (No Action)",
            cost_delta=0.0,
            days_recovered=0.0,
            simulated_finish_date=diff_base.simulated_finish_date,
            remaining_discrete_delayed_count=diff_base.simulated_discrete_delayed_count,
            discrete_delayed_recovered_count=0,
            critical_path_shifted=False,
            levers_applied=[],
            cost_source="ASSUMED_HEURISTIC",
            simulation_diff=diff_base,
        )
    )

    if not cleared_candidates:
        exec_ms = (time.time() - start_time) * 1000.0
        return OptimizationResult(
            project_id=project_id,
            snapshot_id=snapshot_id,
            solver_used="ILP_EXACT",
            budget_limit=budget_limit,
            pareto_frontier=evaluated_points,
            total_scenarios_evaluated=1,
            total_infeasible_rejected=infeasible_count,
            execution_time_ms=exec_ms,
        )

    # 3. Discretize budget into steps from 0 to budget_limit
    step_size = budget_limit / max(1, budget_steps)
    budget_tiers = [step_size * i for i in range(1, budget_steps + 1)]
    seen_lever_sets: Set[Tuple[str, ...]] = set()

    for b_tier in budget_tiers:
        # Formulate 0-1 Knapsack / Selection ILP in PuLP
        prob = pulp.LpProblem(f"TCTP_Tier_{b_tier:.0f}", pulp.LpMaximize)

        # Decision Variables strictly created ONLY for cleared candidates
        var_map: Dict[str, pulp.LpVariable] = {}
        for i, cand in enumerate(cleared_candidates):
            var_name = f"x_{i}_{cand.candidate_id}"
            var_map[cand.candidate_id] = pulp.LpVariable(var_name, cat=pulp.LpBinary)

        # Objective: Maximize nominal time savings with minor tie-breaking penalty on cost
        prob += pulp.lpSum([
            (cand.estimated_time_savings_days * 1000.0 - cand.estimated_cost * 0.001) * var_map[cand.candidate_id]
            for cand in cleared_candidates
        ])

        # Budget constraint
        prob += pulp.lpSum([
            cand.estimated_cost * var_map[cand.candidate_id]
            for cand in cleared_candidates
        ]) <= b_tier

        # Solve PuLP ILP silently
        solver = pulp.PULP_CBC_CMD(msg=False)
        prob.solve(solver)

        if prob.status != pulp.LpStatusOptimal:
            continue

        selected_candidates = [
            cand for cand in cleared_candidates
            if pulp.value(var_map[cand.candidate_id]) is not None and pulp.value(var_map[cand.candidate_id]) > 0.5
        ]

        if not selected_candidates:
            continue

        selected_key = tuple(sorted(cand.candidate_id for cand in selected_candidates))
        if selected_key in seen_lever_sets:
            continue
        seen_lever_sets.add(selected_key)

        # Re-validate full combinatorial lever set
        levers_to_apply = [cand.lever for cand in selected_candidates]
        try:
            validate_lever_set(levers_to_apply, activities, relationships, classifications)
        except Exception:
            infeasible_count += 1
            continue

        # Run authoritative CPM simulation
        sc_name = f"ILP Scenario ({len(selected_candidates)} Levers, Budget ${b_tier:,.0f})"
        sim_res, diff = run_simulation(
            activities, relationships, calendars, options, levers_to_apply, classifications,
            project_data_dates=project_data_dates, project_late_anchors=project_late_anchors,
            scenario_name=sc_name,
        )

        total_cost = sum(cand.estimated_cost for cand in selected_candidates)
        levers_summary = [
            {"candidate_id": cand.candidate_id, "type": cand.lever_type, "target": cand.target_entity, "cost": cand.estimated_cost}
            for cand in selected_candidates
        ]

        evaluated_points.append(
            ParetoPoint(
                scenario_name=sc_name,
                cost_delta=total_cost,
                days_recovered=diff.days_recovered,
                simulated_finish_date=diff.simulated_finish_date,
                remaining_discrete_delayed_count=diff.simulated_discrete_delayed_count,
                discrete_delayed_recovered_count=diff.discrete_delayed_recovered_count,
                critical_path_shifted=diff.critical_path_shifted,
                levers_applied=levers_summary,
                cost_source=selected_candidates[0].cost_source if selected_candidates else "ASSUMED_HEURISTIC",
                simulation_diff=diff,
            )
        )

    # 4. Extract non-dominated Pareto frontier
    pareto_frontier = extract_pareto_frontier(evaluated_points)
    exec_ms = (time.time() - start_time) * 1000.0

    return OptimizationResult(
        project_id=project_id,
        snapshot_id=snapshot_id,
        solver_used="ILP_EXACT",
        budget_limit=budget_limit,
        pareto_frontier=pareto_frontier,
        total_scenarios_evaluated=len(evaluated_points),
        total_infeasible_rejected=infeasible_count,
        execution_time_ms=exec_ms,
    )
