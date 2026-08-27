"""
Unified Optimization Orchestrator.
Generates candidate recovery levers from driver records and routes to ILP or Metaheuristic solvers.
"""

from typing import List, Dict, Tuple, Optional, Any, Set
import time

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.classification import is_fasttrack_candidate, classify_relationship
from arth_rca.db.models import generate_relationship_key, RelationshipClassification
from arth_rca.simulation.levers import CrashLever, FastTrackLever, ConstraintRelaxationLever
from arth_rca.optimization.models import (
    CandidateLeverOption,
    OptimizationRequest,
    OptimizationResult,
    ParetoPoint,
)
from arth_rca.optimization.config import DEFAULT_OPTIMIZATION_CONFIG, OptimizationConfig
from arth_rca.optimization.ilp_solver import solve_ilp_pareto
from arth_rca.optimization.metaheuristic_solver import solve_metaheuristic_pareto


def generate_candidate_levers_for_drivers(
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    classifications: Dict[str, RelationshipClassification],
    target_driver_task_codes: Optional[Set[str]] = None,
    config: Optional[OptimizationConfig] = None,
) -> List[CandidateLeverOption]:
    """
    Generate actionable candidate recovery levers for key driver activities and their interfaces.
    """
    cfg = config or DEFAULT_OPTIMIZATION_CONFIG
    candidates: List[CandidateLeverOption] = []
    task_code_to_act = {act.task_code: act for act in activities.values()}
    act_id_to_act = {act.task_id: act for act in activities.values()}

    # Select target tasks
    if target_driver_task_codes:
        target_acts = [act for code, act in task_code_to_act.items() if code in target_driver_task_codes]
    else:
        # Target activities with negative float or on critical path
        target_acts = [
            act for act in activities.values()
            if act.remaining_duration_days > 0 and act.status != "COMPLETED" and act.task_type not in ("TT_LOE", "TT_WBS")
        ][:15]

    cand_idx = 1
    # 1. Generate Crash Levers on uncompleted activities
    for act in target_acts:
        if act.remaining_duration_days >= 2.0 and not act.is_milestone:
            # Option A: Moderate Crash (approx 30% reduction)
            mod_red = max(1.0, round(act.remaining_duration_days * 0.3, 1))
            c_cost = mod_red * cfg.default_crash_cost_per_day
            candidates.append(
                CandidateLeverOption(
                    candidate_id=f"CRASH_{act.task_code}_{mod_red:.0f}d",
                    lever_type="CRASH",
                    target_entity=act.task_code,
                    lever=CrashLever(
                        task_code=act.task_code,
                        reduction_days=mod_red,
                        cost_delta=c_cost,
                        description=f"Crash duration by {mod_red:.1f}d on {act.task_code}",
                    ),
                    estimated_cost=c_cost,
                    estimated_time_savings_days=mod_red,
                    is_safety_cleared=True,
                    cost_source="ASSUMED_HEURISTIC",
                )
            )
            cand_idx += 1

            # Option B: Aggressive Crash (approx 60% reduction) for longer activities
            if act.remaining_duration_days >= 6.0:
                agg_red = max(2.0, round(act.remaining_duration_days * 0.6, 1))
                c_cost_agg = agg_red * cfg.default_crash_cost_per_day * 1.2  # Overtime premium
                candidates.append(
                    CandidateLeverOption(
                        candidate_id=f"CRASH_AGG_{act.task_code}_{agg_red:.0f}d",
                        lever_type="CRASH",
                        target_entity=act.task_code,
                        lever=CrashLever(
                            task_code=act.task_code,
                            reduction_days=agg_red,
                            cost_delta=c_cost_agg,
                            description=f"Aggressive overtime crash by {agg_red:.1f}d on {act.task_code}",
                        ),
                        estimated_cost=c_cost_agg,
                        estimated_time_savings_days=agg_red,
                        is_safety_cleared=True,
                        cost_source="ASSUMED_HEURISTIC",
                    )
                )
                cand_idx += 1

    # 2. Generate Fast-Track Levers on direct relationships between target activities
    target_tids = {act.task_id for act in target_acts}
    ft_count = 0
    for rel in relationships:
        if rel.rel_type == "FS" and (rel.pred_task_id in target_tids or rel.succ_task_id in target_tids):
            pred_act = act_id_to_act.get(rel.pred_task_id)
            succ_act = act_id_to_act.get(rel.succ_task_id)
            if not pred_act or not succ_act:
                continue

            rel_key = generate_relationship_key(pred_act.task_code, succ_act.task_code, "FS")
            rel_class = classifications.get(rel_key)

            # Check safety clearance
            is_cleared = is_fasttrack_candidate(rel_class)
            ft_cost = cfg.default_fasttrack_coordination_cost
            est_lead = max(1.0, round(pred_act.remaining_duration_days * 0.5, 1))

            candidates.append(
                CandidateLeverOption(
                    candidate_id=f"FT_{pred_act.task_code}_{succ_act.task_code}",
                    lever_type="FAST_TRACK",
                    target_entity=rel_key,
                    lever=FastTrackLever(
                        pred_task_code=pred_act.task_code,
                        succ_task_code=succ_act.task_code,
                        new_relationship_type="SS",
                        new_lag_days=1.0,
                        cost_delta=ft_cost,
                        description=f"Fast-track {pred_act.task_code} -> {succ_act.task_code} to SS+1d",
                    ),
                    estimated_cost=ft_cost,
                    estimated_time_savings_days=est_lead,
                    is_safety_cleared=is_cleared,
                    cost_source="ASSUMED_HEURISTIC",
                )
            )
            cand_idx += 1
            ft_count += 1
            if ft_count >= 15:
                break

    return candidates


def optimize_schedule_recovery(
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
    classifications: Dict[str, RelationshipClassification],
    budget_limit: float = 100000.0,
    project_id: int = 1,
    snapshot_id: int = 1,
    target_driver_task_codes: Optional[Set[str]] = None,
    custom_candidates: Optional[List[CandidateLeverOption]] = None,
    strategy: str = "AUTO",
    project_data_dates: Optional[Dict[int, Any]] = None,
    project_late_anchors: Optional[Dict[int, Any]] = None,
    config: Optional[OptimizationConfig] = None,
) -> OptimizationResult:
    """
    Unified entrypoint to run combinatorial recovery optimization.
    Automatically dispatches to ILP or Metaheuristic solver based on candidate pool size.
    """
    cfg = config or DEFAULT_OPTIMIZATION_CONFIG

    # 1. Prepare candidates
    if custom_candidates:
        candidates = custom_candidates
    else:
        candidates = generate_candidate_levers_for_drivers(
            activities, relationships, classifications, target_driver_task_codes, config=cfg
        )

    # 2. Select Solver
    if strategy == "ILP":
        use_ilp = True
    elif strategy == "METAHEURISTIC":
        use_ilp = False
    else:  # AUTO
        use_ilp = len(candidates) <= cfg.ilp_exact_solver_max_candidates

    if use_ilp:
        return solve_ilp_pareto(
            candidates=candidates,
            activities=activities,
            relationships=relationships,
            calendars=calendars,
            options=options,
            classifications=classifications,
            budget_limit=budget_limit,
            project_id=project_id,
            snapshot_id=snapshot_id,
            project_data_dates=project_data_dates,
            project_late_anchors=project_late_anchors,
        )
    else:
        return solve_metaheuristic_pareto(
            candidates=candidates,
            activities=activities,
            relationships=relationships,
            calendars=calendars,
            options=options,
            classifications=classifications,
            budget_limit=budget_limit,
            project_id=project_id,
            snapshot_id=snapshot_id,
            project_data_dates=project_data_dates,
            project_late_anchors=project_late_anchors,
            config=cfg,
        )
