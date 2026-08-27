"""
Deterministic, calendar-aware CPM engine implemented as a pure function.
Signature: run_cpm(activities, relationships, calendars, options) -> CPMResult
Zero database access, zero side-effects.
Implements exact Primavera P6 F9 multi-calendar scheduling mechanics.
"""

from datetime import datetime, date, timedelta, time
from typing import Dict, List, Set, Optional, Tuple
import networkx as nx

from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
    CPMActivityResult,
    CPMRelationshipResult,
    CPMResult,
    FloatCalcMode,
    OOSMode,
    CriticalPathType,
    DrivingStatus,
)
from arth_rca.cpm.calendar import build_calendar_engine_map, CalendarEngine


# Comprehensive Primavera P6 Constraint Mappings
EARLY_START_CONSTRAINTS = {"CS_START", "CS_SSO", "CS_MSOA", "CS_SNET"}
MANDATORY_START_CONSTRAINTS = {"CS_MANDSTART", "CS_MSTART"}

EARLY_FINISH_CONSTRAINTS = {"CS_FINISH", "CS_FSO", "CS_MEOA", "CS_FNET"}
MANDATORY_FINISH_CONSTRAINTS = {"CS_MANDEND", "CS_MANDFIN", "CS_MEND"}

LATE_FINISH_CONSTRAINTS = {"CS_FINISH", "CS_FSB", "CS_MEOB", "CS_FNLT"}
LATE_START_CONSTRAINTS = {"CS_START", "CS_SSB", "CS_MSOB", "CS_SNLT"}


def run_cpm(
    activities: Dict[int, CPMActivityInput],
    relationships: List[CPMRelationshipInput],
    calendars: Dict[int, CPMCalendarInput],
    options: CPMOptions,
    project_data_dates: Optional[Dict[int, datetime]] = None,
) -> CPMResult:
    """
    Execute deterministic calendar-aware Critical Path Method calculations.
    Pure function with no side effects or external dependencies.
    """
    if not activities:
        now = options.data_date
        return CPMResult(
            activities={},
            relationships={},
            project_early_finish=now,
            project_late_finish=now,
            longest_path_task_ids=[],
        )

    cal_map = build_calendar_engine_map(calendars)
    default_cal = next(iter(cal_map.values()))

    # Build NetworkX graph for topological ordering
    graph = nx.DiGraph()
    for task_id in activities.keys():
        graph.add_node(task_id)

    succ_rels: Dict[int, List[CPMRelationshipInput]] = {tid: [] for tid in activities}
    pred_rels: Dict[int, List[CPMRelationshipInput]] = {tid: [] for tid in activities}

    for rel in relationships:
        if rel.pred_task_id in activities and rel.succ_task_id in activities:
            graph.add_edge(rel.pred_task_id, rel.succ_task_id, rel=rel)
            succ_rels[rel.pred_task_id].append(rel)
            pred_rels[rel.succ_task_id].append(rel)

    # Topological sort
    try:
        topo_order = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        topo_order = list(activities.keys())

    # -------------------------------------------------------------------------
    # 1. FORWARD PASS (Early Start & Early Finish)
    # -------------------------------------------------------------------------
    early_starts: Dict[int, datetime] = {}
    early_finishes: Dict[int, datetime] = {}
    driving_pred_map: Dict[int, Set[int]] = {tid: set() for tid in activities}
    rel_results: Dict[int, CPMRelationshipResult] = {}

    for task_id in topo_order:
        act = activities[task_id]
        cal = cal_map.get(act.calendar_id, default_cal)
        duration = max(0.0, act.remaining_duration_days)
        task_data_date = (
            project_data_dates.get(getattr(act, "proj_id", 0), options.data_date)
            if project_data_dates
            else options.data_date
        )

        # 1.1 Completed Activities
        if act.status == "COMPLETED":
            early_starts[task_id] = task_data_date
            early_finishes[task_id] = task_data_date
            continue

        # 1.2 In-Progress or Unstarted Activities
        candidate_es_list: List[Tuple[datetime, Optional[CPMRelationshipInput]]] = [
            (cal.align_to_work_day_start(task_data_date), None)
        ]

        for rel in pred_rels[task_id]:
            pred_id = rel.pred_task_id
            pred_act = activities[pred_id]
            pred_cal = cal_map.get(pred_act.calendar_id, default_cal)
            lag_days = rel.lag_days

            if options.oos_mode == OOSMode.PROGRESS_OVERRIDE and pred_act.status == "NOT_STARTED" and act.status == "IN_PROGRESS":
                continue

            # P6 Actual Dates Resolution on Completed Predecessors
            if pred_act.status == "COMPLETED":
                hist_finish = min(pred_act.act_finish_date or task_data_date, task_data_date)
                hist_start = min(pred_act.act_start_date or task_data_date, task_data_date)

                if rel.rel_type == "FS":
                    if act.is_milestone or duration == 0.0:
                        nxt = hist_finish
                    elif hist_finish.hour >= 17:
                        nxt = cal.align_to_work_day_start(hist_finish + timedelta(days=1))
                    else:
                        nxt = hist_finish
                    target_start = pred_cal.advance_work_days(nxt, lag_days) if lag_days != 0.0 else nxt
                    aligned_start = cal.align_to_work_day_start(target_start) if not (act.is_milestone and target_start.hour >= 17) else target_start
                    candidate_es_list.append((max(aligned_start, task_data_date), rel))

                elif rel.rel_type == "SS":
                    target_start = pred_cal.advance_work_days(hist_start, lag_days) if lag_days != 0.0 else hist_start
                    aligned_start = cal.align_to_work_day_start(target_start)
                    candidate_es_list.append((max(aligned_start, task_data_date), rel))

                elif rel.rel_type == "FF":
                    target_finish = pred_cal.advance_work_days(hist_finish, lag_days) if lag_days != 0.0 else hist_finish
                    implied_es = cal.subtract_work_days(max(target_finish, task_data_date), duration)
                    candidate_es_list.append((max(implied_es, task_data_date), rel))

                elif rel.rel_type == "SF":
                    target_finish = pred_cal.advance_work_days(hist_start, lag_days) if lag_days != 0.0 else hist_start
                    implied_es = cal.subtract_work_days(max(target_finish, task_data_date), duration)
                    candidate_es_list.append((max(implied_es, task_data_date), rel))

            else:
                # Active or Unstarted Predecessor
                pred_es = early_starts.get(pred_id, task_data_date)
                pred_ef = early_finishes.get(pred_id, task_data_date)

                if rel.rel_type == "FS":
                    if act.is_milestone or duration == 0.0:
                        next_morning = pred_ef
                    elif pred_ef.hour >= 17:
                        next_morning = cal.align_to_work_day_start(pred_ef + timedelta(days=1))
                    else:
                        next_morning = pred_ef
                    target_start = pred_cal.advance_work_days(next_morning, lag_days) if lag_days != 0.0 else next_morning
                    aligned_start = cal.align_to_work_day_start(target_start) if not (act.is_milestone and target_start.hour >= 17) else target_start
                    candidate_es_list.append((aligned_start, rel))

                elif rel.rel_type == "SS":
                    target_start = pred_cal.advance_work_days(pred_es, lag_days) if lag_days != 0.0 else pred_es
                    aligned_start = cal.align_to_work_day_start(target_start)
                    candidate_es_list.append((aligned_start, rel))

                elif rel.rel_type == "FF":
                    target_finish = pred_cal.advance_work_days(pred_ef, lag_days) if lag_days != 0.0 else pred_ef
                    implied_es = cal.subtract_work_days(target_finish, duration)
                    candidate_es_list.append((implied_es, rel))

                elif rel.rel_type == "SF":
                    target_finish = pred_cal.advance_work_days(pred_es, lag_days) if lag_days != 0.0 else pred_es
                    implied_es = cal.subtract_work_days(target_finish, duration)
                    candidate_es_list.append((implied_es, rel))

        max_es = max(item[0] for item in candidate_es_list)
        es = cal.align_to_work_day_start(max(max_es, task_data_date)) if not (act.is_milestone and max_es.hour >= 17) else max_es

        # 1.3 Apply Early Constraints
        if act.cstr_type in MANDATORY_START_CONSTRAINTS and act.cstr_date:
            es = act.cstr_date
        elif act.cstr_type in EARLY_START_CONSTRAINTS and act.cstr_date:
            if act.cstr_date > es:
                es = act.cstr_date

        ef = cal.add_work_days(es, duration)

        # 1.4 Apply Early Finish Constraints
        if act.cstr_type in MANDATORY_FINISH_CONSTRAINTS and act.cstr_date:
            ef = act.cstr_date
            es = cal.subtract_work_days(ef, duration)
        elif act.cstr_type in EARLY_FINISH_CONSTRAINTS and act.cstr_date:
            if act.cstr_date > ef:
                ef = act.cstr_date
                es = cal.subtract_work_days(ef, duration)

        early_starts[task_id] = es
        early_finishes[task_id] = ef

        # 1.5 Evaluate Driving Predecessors
        for cand_date, rel in candidate_es_list:
            if rel is not None:
                if act.status in ("IN_PROGRESS", "COMPLETED") and act.act_start_date:
                    rel_results[rel.rel_id] = CPMRelationshipResult(
                        rel_id=rel.rel_id,
                        pred_task_id=rel.pred_task_id,
                        succ_task_id=rel.succ_task_id,
                        rel_type=rel.rel_type,
                        lag_days=rel.lag_days,
                        is_driving=False,
                        driving_status=DrivingStatus.OVERRIDDEN_BY_ACTUAL_DATE,
                    )
                else:
                    is_driving_edge = cand_date.date() == max_es.date()
                    status = DrivingStatus.DRIVING if is_driving_edge else DrivingStatus.NON_DRIVING
                    rel_results[rel.rel_id] = CPMRelationshipResult(
                        rel_id=rel.rel_id,
                        pred_task_id=rel.pred_task_id,
                        succ_task_id=rel.succ_task_id,
                        rel_type=rel.rel_type,
                        lag_days=rel.lag_days,
                        is_driving=is_driving_edge,
                        driving_status=status,
                    )
                    if is_driving_edge:
                        driving_pred_map[task_id].add(rel.pred_task_id)

    # -------------------------------------------------------------------------
    # 2. BACKWARD PASS (Late Finish & Late Start)
    # -------------------------------------------------------------------------
    late_starts: Dict[int, datetime] = {}
    late_finishes: Dict[int, datetime] = {}

    project_early_finish = max(early_finishes.values()) if early_finishes else options.data_date
    project_late_anchor = options.must_finish_by_date or project_early_finish

    reverse_topo_order = list(reversed(topo_order))

    for task_id in reverse_topo_order:
        act = activities[task_id]
        cal = cal_map.get(act.calendar_id, default_cal)
        is_completed = act.status == "COMPLETED"
        duration = 0.0 if is_completed else max(0.0, act.remaining_duration_days)
        task_data_date = (
            project_data_dates.get(getattr(act, "proj_id", 0), options.data_date)
            if project_data_dates
            else options.data_date
        )

        candidate_lf_list: List[datetime] = []

        outgoing = succ_rels[task_id]
        if not outgoing:
            candidate_lf_list.append(project_late_anchor)
        else:
            for rel in outgoing:
                succ_id = rel.succ_task_id
                succ_act = activities[succ_id]
                succ_cal = cal_map.get(succ_act.calendar_id, default_cal)
                succ_ls = late_starts.get(succ_id, project_late_anchor)
                succ_lf = late_finishes.get(succ_id, project_late_anchor)
                pred_cal = cal
                lag_days = rel.lag_days

                if is_completed and succ_act.status == "COMPLETED":
                    candidate_lf_list.append(succ_ls)
                elif rel.rel_type == "FS":
                    target_start = pred_cal.recede_work_days(succ_ls, lag_days) if lag_days != 0.0 else succ_ls
                    if succ_act.is_milestone or succ_ls.hour >= 17:
                        candidate_lf_list.append(target_start)
                    else:
                        prev_evening = pred_cal.align_to_work_day_end(target_start - timedelta(days=1))
                        candidate_lf_list.append(prev_evening)

                elif rel.rel_type == "SS":
                    target_ls = pred_cal.recede_work_days(succ_ls, lag_days) if lag_days != 0.0 else succ_ls
                    implied_lf = pred_cal.add_work_days(target_ls, duration)
                    candidate_lf_list.append(implied_lf)

                elif rel.rel_type == "FF":
                    target_lf = pred_cal.recede_work_days(succ_lf, lag_days) if lag_days != 0.0 else succ_lf
                    candidate_lf_list.append(target_lf)

                elif rel.rel_type == "SF":
                    target_ls = pred_cal.recede_work_days(succ_lf, lag_days) if lag_days != 0.0 else succ_lf
                    implied_lf = pred_cal.add_work_days(target_ls, duration)
                    candidate_lf_list.append(implied_lf)

        min_lf = min(candidate_lf_list) if candidate_lf_list else project_late_anchor
        lf = cal.align_to_work_day_end(min_lf) if not is_completed else min_lf

        if not is_completed:
            # 2.1 Apply Late Finish Constraints
            if act.cstr_type in MANDATORY_FINISH_CONSTRAINTS and act.cstr_date:
                lf = act.cstr_date
            elif act.cstr_type in LATE_FINISH_CONSTRAINTS and act.cstr_date:
                if act.cstr_date < lf:
                    lf = act.cstr_date

            ls = cal.subtract_work_days(lf, duration)

            # 2.2 Apply Late Start Constraints
            if act.cstr_type in MANDATORY_START_CONSTRAINTS and act.cstr_date:
                ls = act.cstr_date
                lf = cal.add_work_days(ls, duration)
            elif act.cstr_type in LATE_START_CONSTRAINTS and act.cstr_date:
                if act.cstr_date < ls:
                    ls = act.cstr_date
                    lf = cal.add_work_days(ls, duration)
        else:
            ls = lf

        late_starts[task_id] = ls
        late_finishes[task_id] = lf

    project_late_finish = max(late_finishes.values()) if late_finishes else project_late_anchor

    # -------------------------------------------------------------------------
    # 3. FLOAT CALCULATIONS & LONGEST PATH
    # -------------------------------------------------------------------------
    activity_results: Dict[int, CPMActivityResult] = {}

    terminal_anchors = [
        tid for tid, ef in early_finishes.items()
        if ef.date() == project_early_finish.date() and not succ_rels[tid]
    ]
    if not terminal_anchors:
        terminal_anchors = [
            tid for tid, ef in early_finishes.items()
            if ef.date() == project_early_finish.date()
        ]

    longest_path_set: Set[int] = set()
    queue = list(terminal_anchors)
    visited_trace: Set[int] = set()

    while queue:
        curr = queue.pop(0)
        if curr in visited_trace:
            continue
        visited_trace.add(curr)
        longest_path_set.add(curr)

        for pred_id in driving_pred_map.get(curr, []):
            if pred_id not in visited_trace:
                queue.append(pred_id)

    for task_id, act in activities.items():
        cal = cal_map.get(act.calendar_id, default_cal)
        es = early_starts[task_id]
        ef = early_finishes[task_id]
        ls = late_starts[task_id]
        lf = late_finishes[task_id]

        if act.status == "COMPLETED":
            tf = 0.0
            ff = 0.0
        elif act.status == "IN_PROGRESS":
            finish_float = cal.work_days_between(ef, lf)
            tf = finish_float
            ff_candidates: List[float] = []
            for rel in succ_rels[task_id]:
                succ_id = rel.succ_task_id
                succ_es = early_starts.get(succ_id, ef)
                succ_cal = cal_map.get(activities[succ_id].calendar_id, default_cal)
                gap = succ_cal.work_days_between(ef, succ_es) - rel.lag_days
                ff_candidates.append(max(0.0, gap))
            ff = min(ff_candidates) if ff_candidates else max(0.0, tf)
        else:
            start_float = cal.work_days_between(es, ls)
            finish_float = cal.work_days_between(ef, lf)

            if options.f_calc_mode == FloatCalcMode.FINISH_DATES:
                tf = finish_float
            elif options.f_calc_mode == FloatCalcMode.MIN_START_FINISH:
                tf = min(start_float, finish_float)
            else:
                tf = start_float

            ff_candidates: List[float] = []
            for rel in succ_rels[task_id]:
                succ_id = rel.succ_task_id
                succ_es = early_starts.get(succ_id, ef)
                succ_cal = cal_map.get(activities[succ_id].calendar_id, default_cal)
                gap = succ_cal.work_days_between(ef, succ_es) - rel.lag_days
                ff_candidates.append(max(0.0, gap))

            ff = min(ff_candidates) if ff_candidates else max(0.0, tf)

        is_on_longest_path = task_id in longest_path_set
        if options.critical_path_type == CriticalPathType.LONGEST_PATH:
            is_critical = is_on_longest_path
        else:
            is_critical = tf <= options.critical_float_threshold_days

        activity_results[task_id] = CPMActivityResult(
            task_id=task_id,
            task_code=act.task_code,
            early_start=es,
            early_finish=ef,
            late_start=ls,
            late_finish=lf,
            total_float_days=tf,
            free_float_days=ff,
            is_critical=is_critical,
            driving_path_flag=is_on_longest_path,
        )

    return CPMResult(
        activities=activity_results,
        relationships=rel_results,
        project_early_finish=project_early_finish,
        project_late_finish=project_late_finish,
        longest_path_task_ids=list(longest_path_set),
    )
