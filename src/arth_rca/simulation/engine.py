"""
What-If / Recovery Simulation Engine.
Applies recovery levers onto cloned schedule graphs, validates safety gates,
recomputes CPM math using the Phase 0 pure-function engine, and computes diffs
using discrete denominator discipline.
"""

import copy
import dataclasses
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
import networkx as nx
from pydantic import BaseModel, Field

from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.calendar import CalendarEngine
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
    CPMResult,
)
from arth_rca.analytics.classification import is_fasttrack_candidate
from arth_rca.db.models import (
    RelationshipClassification,
    generate_relationship_key,
)
from arth_rca.simulation.levers import (
    AnyLever,
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
    validate_transitive_independence,
)


class ActivityFloatDelta(BaseModel):
    task_id: int
    task_code: str
    baseline_total_float_days: float
    simulated_total_float_days: float
    float_delta_days: float
    baseline_early_finish: str
    simulated_early_finish: str
    is_discrete: bool = True


class SimulationDiffResult(BaseModel):
    scenario_name: str = "Recovery Scenario"
    baseline_finish_date: str
    simulated_finish_date: str
    days_recovered: float
    critical_path_shifted: bool = False
    baseline_discrete_delayed_count: int
    simulated_discrete_delayed_count: int
    discrete_delayed_recovered_count: int
    total_delayed_count_with_loe: int
    total_cost_delta: float = 0.0
    status: str = "proposed"  # proposed | pending_approval | approved | rejected
    requires_pm_approval: bool = False
    levers_applied_count: int = 0
    activity_deltas: List[ActivityFloatDelta] = Field(default_factory=list)


def clone_schedule_inputs(
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
) -> Tuple[Dict[int, CPMActivityInput], List[CPMRelationshipInput], Dict[int, CPMCalendarInput], CPMOptions]:
    """Deep clone all CPM input structures to guarantee immutability of the baseline."""
    cloned_acts = {k: copy.deepcopy(v) for k, v in activities.items()}
    cloned_rels = [copy.deepcopy(r) for r in relationships]
    cloned_cals = {k: copy.deepcopy(v) for k, v in calendars.items()}
    cloned_opts = copy.deepcopy(options)
    return cloned_acts, cloned_rels, cloned_cals, cloned_opts


def build_dependency_dag(activities: Dict[int, CPMActivityInput], relationships: List[CPMRelationshipInput]) -> nx.DiGraph:
    """Build a NetworkX DiGraph representing the schedule network."""
    G = nx.DiGraph()
    for tid in activities:
        G.add_node(tid)
    for r in relationships:
        G.add_edge(r.pred_task_id, r.succ_task_id, rel_type=r.rel_type, lag_days=r.lag_days)
    return G


def validate_lever_set(
    levers: List[AnyLever],
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    classifications: Dict[str, Any],
) -> nx.DiGraph:
    """
    Validate all levers individually AND combinatorially as a complete set.
    Ensures no safety violations, no cross-lever conflicts, and no graph cycles.
    """
    task_code_to_id = {act.task_code: tid for tid, act in activities.items()}
    graph = build_dependency_dag(activities, relationships)

    # Track touched entities for conflict detection
    touched_rel_keys: Set[str] = set()
    touched_activities: Set[str] = set()

    for lever in levers:
        if isinstance(lever, CrashLever):
            if lever.task_code not in task_code_to_id:
                raise ValueError(f"CrashLever target task '{lever.task_code}' not found.")
            act = activities[task_code_to_id[lever.task_code]]
            if act.remaining_duration_days <= 0.0:
                raise ValueError(f"Cannot crash zero-duration task '{lever.task_code}'.")
            touched_activities.add(lever.task_code)

        elif isinstance(lever, FastTrackLever):
            if lever.pred_task_code not in task_code_to_id or lever.succ_task_code not in task_code_to_id:
                raise ValueError(f"FastTrackLever tasks '{lever.pred_task_code}' -> '{lever.succ_task_code}' not found.")
            
            rel_key = generate_relationship_key(lever.pred_task_code, lever.succ_task_code, "FS")
            if rel_key in touched_rel_keys:
                raise CombinatorialConflictError(f"Multiple conflicting levers applied to relationship '{rel_key}'.")
            touched_rel_keys.add(rel_key)

            # Strict Safety Gate Check
            rel_class = classifications.get(rel_key)
            if not is_fasttrack_candidate(rel_class):
                ctype = getattr(rel_class, "constraint_type", "UNCLASSIFIED") if rel_class else "UNCLASSIFIED"
                raise SafetyViolationError(
                    f"Safety Violation: Cannot fast-track relationship '{lever.pred_task_code}' -> '{lever.succ_task_code}'. "
                    f"Constraint type is '{ctype}', which is legally/physically locked."
                )

        elif isinstance(lever, ResequencingLever):
            if lever.task_a_code not in task_code_to_id or lever.task_b_code not in task_code_to_id:
                raise ValueError(f"Resequencing tasks '{lever.task_a_code}' and '{lever.task_b_code}' not found.")
            tid_a = task_code_to_id[lever.task_a_code]
            tid_b = task_code_to_id[lever.task_b_code]

            # Transitive independence check
            if not validate_transitive_independence(graph, tid_a, tid_b):
                raise DependencyViolationError(
                    f"Cannot resequence '{lever.task_a_code}' and '{lever.task_b_code}': "
                    f"A transitive dependency path already exists between them in the schedule network."
                )

        elif isinstance(lever, LogicChangeLever):
            rel_key = generate_relationship_key(lever.pred_task_code, lever.succ_task_code, lever.relationship_type)
            if rel_key in touched_rel_keys:
                raise CombinatorialConflictError(f"Multiple conflicting logic levers applied to '{rel_key}'.")
            touched_rel_keys.add(rel_key)

    return graph


def apply_levers(
    cloned_acts: Dict[int, CPMActivityInput],
    cloned_rels: List[CPMRelationshipInput],
    cloned_cals: Dict[int, CPMCalendarInput],
    levers: List[AnyLever],
    classifications: Dict[str, Any],
) -> List[CPMRelationshipInput]:
    """Apply validated recovery levers onto cloned schedule structures."""
    task_code_to_id = {act.task_code: tid for tid, act in cloned_acts.items()}
    new_rels = list(cloned_rels)

    for lever in levers:
        if isinstance(lever, CrashLever):
            tid = task_code_to_id[lever.task_code]
            act = cloned_acts[tid]
            new_dur = max(0.0, act.remaining_duration_days - lever.reduction_days)
            cloned_acts[tid] = dataclasses.replace(act, remaining_duration_days=new_dur)

        elif isinstance(lever, FastTrackLever):
            pred_id = task_code_to_id[lever.pred_task_code]
            succ_id = task_code_to_id[lever.succ_task_code]
            for r in new_rels:
                if r.pred_task_id == pred_id and r.succ_task_id == succ_id and r.rel_type == "FS":
                    r.rel_type = lever.new_relationship_type
                    r.lag_days = lever.new_lag_days
                    break

        elif isinstance(lever, LogicChangeLever):
            pred_id = task_code_to_id[lever.pred_task_code]
            succ_id = task_code_to_id[lever.succ_task_code]
            if lever.action == "REMOVE":
                new_rels = [r for r in new_rels if not (r.pred_task_id == pred_id and r.succ_task_id == succ_id)]
            elif lever.action == "ADD":
                new_rels.append(
                    CPMRelationshipInput(
                        rel_id=max([r.rel_id for r in new_rels] + [0]) + 1,
                        pred_task_id=pred_id,
                        succ_task_id=succ_id,
                        rel_type=lever.relationship_type,
                        lag_days=lever.lag_days,
                    )
                )
            elif lever.action == "MODIFY":
                for r in new_rels:
                    if r.pred_task_id == pred_id and r.succ_task_id == succ_id:
                        r.rel_type = lever.relationship_type
                        r.lag_days = lever.lag_days
                        break

        elif isinstance(lever, ConstraintRelaxationLever):
            tid = task_code_to_id[lever.task_code]
            act = cloned_acts[tid]
            if lever.action == "REMOVE":
                cloned_acts[tid] = dataclasses.replace(act, cstr_type=None, cstr_date=None)
            elif lever.action == "RELAX_DATE" and lever.new_constraint_date:
                cloned_acts[tid] = dataclasses.replace(act, cstr_date=datetime.fromisoformat(lever.new_constraint_date))

        elif isinstance(lever, ResequencingLever):
            tid_a = task_code_to_id[lever.task_a_code]
            tid_b = task_code_to_id[lever.task_b_code]
            if lever.new_order == "A_THEN_B":
                new_rels.append(CPMRelationshipInput(rel_id=999999, pred_task_id=tid_a, succ_task_id=tid_b, rel_type="FS", lag_days=0.0))
            elif lever.new_order == "B_THEN_A":
                new_rels.append(CPMRelationshipInput(rel_id=999999, pred_task_id=tid_b, succ_task_id=tid_a, rel_type="FS", lag_days=0.0))

        elif isinstance(lever, CalendarChangeLever):
            tid = task_code_to_id[lever.task_code]
            act = cloned_acts[tid]
            cloned_acts[tid] = dataclasses.replace(act, calendar_id=lever.new_calendar_id)

        elif isinstance(lever, ActivitySplitLever):
            tid = task_code_to_id[lever.task_code]
            act = cloned_acts[tid]
            cloned_acts[tid] = dataclasses.replace(act, remaining_duration_days=act.remaining_duration_days / lever.split_count)

    # Final combinatorial cycle check on the mutated network
    mutated_graph = build_dependency_dag(cloned_acts, new_rels)
    if not nx.is_directed_acyclic_graph(mutated_graph):
        cycles = list(nx.simple_cycles(mutated_graph))
        raise CombinatorialConflictError(f"Lever set created a circular logic loop in schedule network: {cycles[:3]}")

    return new_rels


def run_simulation(
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
    levers: List[AnyLever],
    classifications: Optional[Dict[str, Any]] = None,
    project_data_dates: Optional[Dict[int, datetime]] = None,
    project_late_anchors: Optional[Dict[int, datetime]] = None,
    scenario_name: str = "Recovery Scenario",
    scoped_preview: bool = False,
    baseline_cpm_result: Optional[CPMResult] = None,
) -> Tuple[CPMResult, SimulationDiffResult]:
    """
    Run a full recovery simulation scenario with discrete denominator discipline.
    """
    class_map = classifications or {}
    # 1. Full lever-set validation
    validate_lever_set(levers, activities, relationships, class_map)

    # 2. Clone inputs
    cloned_acts, cloned_rels, cloned_cals, cloned_opts = clone_schedule_inputs(activities, relationships, calendars, options)

    # 3. Apply levers
    mutated_rels = apply_levers(cloned_acts, cloned_rels, cloned_cals, levers, class_map)

    # 4. Compute baseline if not provided
    if not baseline_cpm_result:
        baseline_cpm_result = run_cpm(
            activities, relationships, calendars, options,
            project_data_dates=project_data_dates, project_late_anchors=project_late_anchors
        )

    # 5. Run CPM engine
    sim_cpm_result = run_cpm(
        cloned_acts, mutated_rels, cloned_cals, cloned_opts,
        project_data_dates=project_data_dates, project_late_anchors=project_late_anchors
    )

    # 6. Baseline vs Simulated Finish Dates
    base_max_ef = max((res.early_finish for res in baseline_cpm_result.activities.values()), default=options.data_date)
    sim_max_ef = max((res.early_finish for res in sim_cpm_result.activities.values()), default=options.data_date)

    # Compute working days recovered
    default_c = next(iter(calendars.values()), None)
    if default_c and sim_max_ef < base_max_ef:
        cal_obj = CalendarEngine(default_c)
        curr = sim_max_ef.date()
        target = base_max_ef.date()
        work_days = 0
        while curr < target:
            curr += timedelta(days=1)
            if cal_obj.is_work_day(curr):
                work_days += 1
        days_recovered = float(work_days)
    else:
        days_recovered = (base_max_ef - sim_max_ef).total_seconds() / 86400.0

    # 7. Check if critical path shifted
    base_cp = {tid for tid, res in baseline_cpm_result.activities.items() if res.is_critical}
    sim_cp = {tid for tid, res in sim_cpm_result.activities.items() if res.is_critical}
    cp_shifted = (base_cp != sim_cp)

    # 8. Discrete Denominator Discipline: filter out LOE/WBS summary tasks
    # Non-completed discrete activities
    discrete_tids = {
        tid for tid, act in activities.items() 
        if act.status != "COMPLETED" and getattr(act, "task_type", "") not in ("TT_LOE", "TT_WBS")
    }

    base_discrete_delayed = sum(
        1 for tid in discrete_tids if baseline_cpm_result.activities[tid].total_float_days < -0.01
    )
    sim_discrete_delayed = sum(
        1 for tid in discrete_tids if sim_cpm_result.activities[tid].total_float_days < -0.01
    )
    discrete_recovered_count = max(0, base_discrete_delayed - sim_discrete_delayed)

    total_delayed_with_loe = sum(
        1 for tid, res in sim_cpm_result.activities.items() 
        if activities[tid].status != "COMPLETED" and res.total_float_days < -0.01
    )

    # 9. Approval status tracking
    requires_approval = any(getattr(l, "requires_pm_approval", False) for l in levers)
    all_approved = all(getattr(l, "approved_by", None) is not None for l in levers if getattr(l, "requires_pm_approval", False))
    status = "approved" if (not requires_approval or all_approved) else "pending_approval"

    # 10. Cost delta
    total_cost_delta = sum(getattr(l, "cost_delta", 0.0) for l in levers)

    # 11. Activity deltas
    deltas: List[ActivityFloatDelta] = []
    for tid, act in activities.items():
        base_res = baseline_cpm_result.activities[tid]
        sim_res = sim_cpm_result.activities[tid]
        f_delta = sim_res.total_float_days - base_res.total_float_days
        if abs(f_delta) > 0.001 or base_res.early_finish != sim_res.early_finish:
            deltas.append(
                ActivityFloatDelta(
                    task_id=tid,
                    task_code=act.task_code,
                    baseline_total_float_days=base_res.total_float_days,
                    simulated_total_float_days=sim_res.total_float_days,
                    float_delta_days=f_delta,
                    baseline_early_finish=base_res.early_finish.isoformat(),
                    simulated_early_finish=sim_res.early_finish.isoformat(),
                    is_discrete=(tid in discrete_tids),
                )
            )

    diff = SimulationDiffResult(
        scenario_name=scenario_name,
        baseline_finish_date=base_max_ef.isoformat(),
        simulated_finish_date=sim_max_ef.isoformat(),
        days_recovered=round(days_recovered, 2),
        critical_path_shifted=cp_shifted,
        baseline_discrete_delayed_count=base_discrete_delayed,
        simulated_discrete_delayed_count=sim_discrete_delayed,
        discrete_delayed_recovered_count=discrete_recovered_count,
        total_delayed_count_with_loe=total_delayed_with_loe,
        total_cost_delta=total_cost_delta,
        status=status,
        requires_pm_approval=requires_approval,
        levers_applied_count=len(levers),
        activity_deltas=deltas,
    )

    return sim_cpm_result, diff
