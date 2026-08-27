"""
Historical Trend Aggregator across sequential snapshots.
Tracks milestone cumulative slippages, DCMA 14-point metric history,
activity float erosion, and driver churn strictly as historical facts.
EXPLICITLY ZERO PREDICTION, EXTRAPOLATION, OR FORECASTING.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions, CPMResult
from arth_rca.cpm.engine import run_cpm
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.dcma import run_dcma_14_point_assessment, DCMAAssessmentReport, DCMAMetricResult
from arth_rca.analytics.snapshot_diff import compute_snapshot_diff, DriverChurn


class SnapshotMeta(BaseModel):
    snapshot_id: int
    data_date: datetime
    is_baseline: bool = False
    source_filename: Optional[str] = None


class MilestoneHistoricalPoint(BaseModel):
    snapshot_id: int
    data_date: datetime
    early_finish: Optional[datetime] = None
    total_float_days: Optional[float] = None
    cumulative_slippage_days: float = 0.0
    status: str = "NOT_STARTED"


class MilestoneTrendSeries(BaseModel):
    task_code: str
    milestone_name: str
    baseline_early_finish: Optional[datetime] = None
    history: List[MilestoneHistoricalPoint] = Field(default_factory=list)
    net_cumulative_slippage_days: float = 0.0


class DCMAHistoricalPoint(BaseModel):
    snapshot_id: int
    data_date: datetime
    overall_health_score: float
    logic_missing_predecessors_count: int
    logic_missing_successors_count: int
    negative_float_activities_count: int
    hard_constraints_count: int
    negative_lags_count: int
    high_float_count: int
    critical_path_length_index: Optional[float] = None


class FloatErosionHistoricalPoint(BaseModel):
    snapshot_id: int
    data_date: datetime
    total_float_days: Optional[float] = None
    remaining_duration_days: float = 0.0
    status: str = "NOT_STARTED"


class ActivityFloatTrend(BaseModel):
    task_code: str
    activity_name: str
    history: List[FloatErosionHistoricalPoint] = Field(default_factory=list)
    net_float_erosion_days: float = 0.0


class DriverChurnStep(BaseModel):
    from_snapshot_id: int
    to_snapshot_id: int
    to_data_date: datetime
    churn: DriverChurn


class HistoricalTrendPayload(BaseModel):
    project_id: int
    total_snapshots: int
    snapshots: List[SnapshotMeta] = Field(default_factory=list)
    milestone_trends: List[MilestoneTrendSeries] = Field(default_factory=list)
    dcma_history: List[DCMAHistoricalPoint] = Field(default_factory=list)
    driver_float_trends: List[ActivityFloatTrend] = Field(default_factory=list)
    driver_churn_progression: List[DriverChurnStep] = Field(default_factory=list)


class SnapshotDataPackage(BaseModel):
    snapshot_id: int
    data_date: datetime
    is_baseline: bool = False
    source_filename: Optional[str] = None
    activities: Dict[int, CPMActivityInput]
    relationships: List[CPMRelationshipInput]
    calendars: Dict[int, CPMCalendarInput]
    options: CPMOptions
    project_data_dates: Optional[Dict[int, Any]] = None
    project_late_anchors: Optional[Dict[int, Any]] = None


def aggregate_historical_trends(
    project_id: int,
    snapshots: List[SnapshotDataPackage],
    target_milestone_task_codes: Optional[List[str]] = None,
    target_driver_task_codes: Optional[List[str]] = None,
) -> HistoricalTrendPayload:
    """
    Aggregates historical trend data across sequentially ordered snapshots.
    Guaranteed deterministic historical diffing with zero forecasting/extrapolation.
    """
    if not snapshots:
        return HistoricalTrendPayload(project_id=project_id, total_snapshots=0)

    # 1. Sort snapshots strictly by data_date
    sorted_snaps = sorted(snapshots, key=lambda s: s.data_date)

    # 2. Run CPM and DCMA for each snapshot
    cpm_results: List[CPMResult] = []
    dcma_results: List[DCMAResult] = []
    meta_list: List[SnapshotMeta] = []

    for s in sorted_snaps:
        cpm_res = run_cpm(
            s.activities,
            s.relationships,
            s.calendars,
            s.options,
            project_data_dates=s.project_data_dates,
            project_late_anchors=s.project_late_anchors,
        )
        cpm_results.append(cpm_res)

        class TaskWrapper:
            def __init__(self, act: CPMActivityInput):
                self.task_id = act.task_id
                self.task_code = act.task_code
                self.status_code = "TK_Complete" if act.status == "COMPLETED" else ("TK_Active" if act.status == "IN_PROGRESS" else "TK_NotStart")
                self.task_type = "TT_FinMile" if act.is_milestone else "TT_Task"
                self.cstr_type = act.cstr_type
                self.cstr_date = act.cstr_date
                self.target_durn_hr_cnt = act.original_duration_days * 8.0
                self.act_start_date = act.act_start_date
                self.act_end_date = act.act_finish_date

        raw_tasks_dict = {tid: TaskWrapper(act) for tid, act in s.activities.items()}
        dcma_res = run_dcma_14_point_assessment(
            cpm_result=cpm_res,
            raw_tasks=raw_tasks_dict,
            raw_relationships=s.relationships,
            data_date=s.data_date,
            snapshot_id=s.snapshot_id,
        )
        dcma_results.append(dcma_res)

        meta_list.append(
            SnapshotMeta(
                snapshot_id=s.snapshot_id,
                data_date=s.data_date,
                is_baseline=s.is_baseline,
                source_filename=s.source_filename,
            )
        )

    # 3. DCMA Historical Score Progression
    dcma_history: List[DCMAHistoricalPoint] = []
    for idx, s in enumerate(sorted_snaps):
        d_res = dcma_results[idx]
        metrics_by_num = {m.check_number: m for m in d_res.metrics}

        dcma_history.append(
            DCMAHistoricalPoint(
                snapshot_id=s.snapshot_id,
                data_date=s.data_date,
                overall_health_score=d_res.overall_health_score,
                logic_missing_predecessors_count=metrics_by_num.get(1, DCMAMetricResult(check_number=1, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                logic_missing_successors_count=metrics_by_num.get(1, DCMAMetricResult(check_number=1, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                negative_float_activities_count=metrics_by_num.get(7, DCMAMetricResult(check_number=7, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                hard_constraints_count=metrics_by_num.get(5, DCMAMetricResult(check_number=5, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                negative_lags_count=metrics_by_num.get(2, DCMAMetricResult(check_number=2, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                high_float_count=metrics_by_num.get(6, DCMAMetricResult(check_number=6, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).failing_activity_count,
                critical_path_length_index=metrics_by_num.get(13, DCMAMetricResult(check_number=13, name="", target_threshold="", actual_value=0, passed=True, failing_activity_count=0, total_applicable_count=0)).actual_value,
            )
        )

    # 4. Milestone Cumulative Slippage History
    # Baseline snapshot is first snapshot or flagged baseline
    baseline_idx = 0
    for idx, s in enumerate(sorted_snaps):
        if s.is_baseline:
            baseline_idx = idx
            break

    baseline_snap = sorted_snaps[baseline_idx]
    baseline_cpm = cpm_results[baseline_idx]
    baseline_acts = {act.task_code: (act, baseline_cpm.activities.get(act.task_id)) for act in baseline_snap.activities.values()}

    # Identify all milestones across snapshots
    all_milestone_codes: Set[str] = set()
    for s in sorted_snaps:
        for act in s.activities.values():
            if act.is_milestone or 'Mile' in (act.task_type or ''):
                if not target_milestone_task_codes or act.task_code in target_milestone_task_codes:
                    all_milestone_codes.add(act.task_code)

    milestone_trends: List[MilestoneTrendSeries] = []
    for m_code in sorted(all_milestone_codes):
        base_tuple = baseline_acts.get(m_code)
        base_ef = base_tuple[1].early_finish if (base_tuple and base_tuple[1]) else None
        m_name = getattr(base_tuple[0], "name", None) or m_code if base_tuple else m_code

        m_history: List[MilestoneHistoricalPoint] = []
        for idx, s in enumerate(sorted_snaps):
            cpm_res = cpm_results[idx]
            act_match = next((act for act in s.activities.values() if act.task_code == m_code), None)
            if not act_match:
                continue

            cpm_act = cpm_res.activities.get(act_match.task_id)
            cur_ef = cpm_act.early_finish if cpm_act else None
            cur_tf = cpm_act.total_float_days if cpm_act else None

            # Point-to-point cumulative slippage relative to baseline
            slip_days = 0.0
            if base_ef and cur_ef:
                slip_days = round((cur_ef - base_ef).total_seconds() / 86400.0, 1)

            m_history.append(
                MilestoneHistoricalPoint(
                    snapshot_id=s.snapshot_id,
                    data_date=s.data_date,
                    early_finish=cur_ef,
                    total_float_days=cur_tf,
                    cumulative_slippage_days=slip_days,
                    status=act_match.status,
                )
            )

        net_slip = m_history[-1].cumulative_slippage_days if m_history else 0.0
        milestone_trends.append(
            MilestoneTrendSeries(
                task_code=m_code,
                milestone_name=m_name,
                baseline_early_finish=base_ef,
                history=m_history,
                net_cumulative_slippage_days=net_slip,
            )
        )

    # 5. Activity Float Erosion History
    all_driver_codes: Set[str] = set()
    if target_driver_task_codes:
        all_driver_codes.update(target_driver_task_codes)
    else:
        # Collect top negative float drivers across all snapshots
        for idx, s in enumerate(sorted_snaps):
            cpm_res = cpm_results[idx]
            d_res = detect_negative_float_drivers(cpm_res, s.activities, s.relationships)
            for dh in d_res.drivers[:10]:
                all_driver_codes.add(dh.driver_task_code)

    driver_float_trends: List[ActivityFloatTrend] = []
    for d_code in sorted(all_driver_codes):
        d_history: List[FloatErosionHistoricalPoint] = []
        d_name = d_code
        for idx, s in enumerate(sorted_snaps):
            cpm_res = cpm_results[idx]
            act_match = next((act for act in s.activities.values() if act.task_code == d_code), None)
            if not act_match:
                continue

            d_name = getattr(act_match, "name", None) or d_code
            cpm_act = cpm_res.activities.get(act_match.task_id)
            cur_tf = cpm_act.total_float_days if cpm_act else None

            d_history.append(
                FloatErosionHistoricalPoint(
                    snapshot_id=s.snapshot_id,
                    data_date=s.data_date,
                    total_float_days=cur_tf,
                    remaining_duration_days=act_match.remaining_duration_days,
                    status=act_match.status,
                )
            )

        net_erosion = 0.0
        if len(d_history) >= 2 and d_history[0].total_float_days is not None and d_history[-1].total_float_days is not None:
            net_erosion = round(d_history[0].total_float_days - d_history[-1].total_float_days, 2)

        driver_float_trends.append(
            ActivityFloatTrend(
                task_code=d_code,
                activity_name=d_name,
                history=d_history,
                net_float_erosion_days=net_erosion,
            )
        )

    # 6. Driver Churn Progression between adjacent pairs
    churn_steps: List[DriverChurnStep] = []
    for i in range(len(sorted_snaps) - 1):
        s_prev = sorted_snaps[i]
        s_next = sorted_snaps[i + 1]
        diff_res = compute_snapshot_diff(
            acts_a=s_prev.activities,
            rels_a=s_prev.relationships,
            cals_a=s_prev.calendars,
            options_a=s_prev.options,
            acts_b=s_next.activities,
            rels_b=s_next.relationships,
            cals_b=s_next.calendars,
            options_b=s_next.options,
            snapshot_a_id=s_prev.snapshot_id,
            snapshot_b_id=s_next.snapshot_id,
            project_data_dates_a=s_prev.project_data_dates,
            project_data_dates_b=s_next.project_data_dates,
            project_late_anchors_a=s_prev.project_late_anchors,
            project_late_anchors_b=s_next.project_late_anchors,
        )
        churn_steps.append(
            DriverChurnStep(
                from_snapshot_id=s_prev.snapshot_id,
                to_snapshot_id=s_next.snapshot_id,
                to_data_date=s_next.data_date,
                churn=diff_res.driver_churn,
            )
        )

    return HistoricalTrendPayload(
        project_id=project_id,
        total_snapshots=len(sorted_snaps),
        snapshots=meta_list,
        milestone_trends=milestone_trends,
        dcma_history=dcma_history,
        driver_float_trends=driver_float_trends,
        driver_churn_progression=churn_steps,
    )
