"""
Deterministic Snapshot-to-Snapshot Diff Engine and Driver Churn Tracker.
Compares two project schedule snapshots to detect added/removed/modified activities,
relationship modifications, constraint changes, and discrete driver churn.
"""

from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field

from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions, CPMResult
from arth_rca.cpm.engine import run_cpm
from arth_rca.analytics.driver_detection import detect_negative_float_drivers, DrivingChainTree
from arth_rca.db.models import generate_relationship_key


class ActivityDiff(BaseModel):
    task_code: str
    name_before: Optional[str] = None
    name_after: Optional[str] = None
    change_type: str = Field(..., description="ADDED, REMOVED, MODIFIED, UNCHANGED")
    duration_delta_days: float = 0.0
    remaining_duration_delta_days: float = 0.0
    total_float_before: Optional[float] = None
    total_float_after: Optional[float] = None
    total_float_delta_days: Optional[float] = None
    status_before: Optional[str] = None
    status_after: Optional[str] = None
    constraint_type_before: Optional[str] = None
    constraint_type_after: Optional[str] = None
    constraint_date_before: Optional[datetime] = None
    constraint_date_after: Optional[datetime] = None
    early_finish_before: Optional[datetime] = None
    early_finish_after: Optional[datetime] = None
    early_finish_delta_days: float = 0.0


class RelationshipDiff(BaseModel):
    relationship_key: str
    pred_task_code: str
    succ_task_code: str
    change_type: str = Field(..., description="ADDED, REMOVED, MODIFIED, UNCHANGED")
    rel_type_before: Optional[str] = None
    rel_type_after: Optional[str] = None
    lag_before: Optional[float] = None
    lag_after: Optional[float] = None
    lag_delta_days: float = 0.0


class DriverChurn(BaseModel):
    new_drivers: List[str] = Field(default_factory=list, description="Driver heads newly emerging with negative float in Snapshot B")
    resolved_drivers: List[str] = Field(default_factory=list, description="Driver heads in Snapshot A that have recovered to TF >= 0 or completed in Snapshot B")
    persistent_drivers: List[str] = Field(default_factory=list, description="Driver heads present in both Snapshot A and Snapshot B with negative float")
    persistent_driver_float_deltas: Dict[str, float] = Field(default_factory=dict, description="Float delta (TF_B - TF_A) for persistent drivers")


class SnapshotDiffResult(BaseModel):
    snapshot_a_id: Optional[int] = None
    snapshot_b_id: Optional[int] = None
    snapshot_a_data_date: Optional[datetime] = None
    snapshot_b_data_date: Optional[datetime] = None
    
    total_activities_a: int = 0
    total_activities_b: int = 0
    added_activities_count: int = 0
    removed_activities_count: int = 0
    modified_activities_count: int = 0
    
    total_relationships_a: int = 0
    total_relationships_b: int = 0
    added_relationships_count: int = 0
    removed_relationships_count: int = 0
    modified_relationships_count: int = 0
    
    activity_diffs: List[ActivityDiff] = Field(default_factory=list)
    relationship_diffs: List[RelationshipDiff] = Field(default_factory=list)
    driver_churn: DriverChurn = Field(default_factory=DriverChurn)
    
    discrete_delayed_count_a: int = 0
    discrete_delayed_count_b: int = 0
    discrete_delayed_net_delta: int = 0
    
    project_finish_date_a: Optional[datetime] = None
    project_finish_date_b: Optional[datetime] = None
    project_finish_slippage_days: float = 0.0


def compute_snapshot_diff(
    acts_a: Dict[int, CPMActivityInput],
    rels_a: List[CPMRelationshipInput],
    cals_a: Dict[int, CPMCalendarInput],
    options_a: CPMOptions,
    acts_b: Dict[int, CPMActivityInput],
    rels_b: List[CPMRelationshipInput],
    cals_b: Dict[int, CPMCalendarInput],
    options_b: CPMOptions,
    snapshot_a_id: Optional[int] = None,
    snapshot_b_id: Optional[int] = None,
    project_data_dates_a: Optional[Dict[int, Any]] = None,
    project_data_dates_b: Optional[Dict[int, Any]] = None,
    project_late_anchors_a: Optional[Dict[int, Any]] = None,
    project_late_anchors_b: Optional[Dict[int, Any]] = None,
) -> SnapshotDiffResult:
    """
    Computes a deterministic diff between two schedule snapshots.
    Reuses pure CPM engine and discrete driver detection.
    """
    # 1. Run CPM on both snapshots
    cpm_a = run_cpm(acts_a, rels_a, cals_a, options_a, project_data_dates=project_data_dates_a, project_late_anchors=project_late_anchors_a)
    cpm_b = run_cpm(acts_b, rels_b, cals_b, options_b, project_data_dates=project_data_dates_b, project_late_anchors=project_late_anchors_b)

    # 2. Map activities by stable task_code
    code_to_act_a = {act.task_code: act for act in acts_a.values()}
    code_to_act_b = {act.task_code: act for act in acts_b.values()}
    all_codes = set(code_to_act_a.keys()).union(set(code_to_act_b.keys()))

    activity_diffs: List[ActivityDiff] = []
    added_acts = 0
    removed_acts = 0
    modified_acts = 0

    for code in sorted(all_codes):
        in_a = code in code_to_act_a
        in_b = code in code_to_act_b

        if in_a and not in_b:
            act_a = code_to_act_a[code]
            cpm_act_a = cpm_a.activities.get(act_a.task_id)
            activity_diffs.append(
                ActivityDiff(
                    task_code=code,
                    name_before=getattr(act_a, "name", None) or act_a.task_code,
                    change_type="REMOVED",
                    duration_delta_days=-act_a.original_duration_days,
                    remaining_duration_delta_days=-act_a.remaining_duration_days,
                    total_float_before=cpm_act_a.total_float_days if cpm_act_a else None,
                    status_before=act_a.status,
                    constraint_type_before=act_a.cstr_type,
                    constraint_date_before=act_a.cstr_date,
                    early_finish_before=cpm_act_a.early_finish if cpm_act_a else None,
                )
            )
            removed_acts += 1

        elif in_b and not in_a:
            act_b = code_to_act_b[code]
            cpm_act_b = cpm_b.activities.get(act_b.task_id)
            activity_diffs.append(
                ActivityDiff(
                    task_code=code,
                    name_after=getattr(act_b, "name", None) or act_b.task_code,
                    change_type="ADDED",
                    duration_delta_days=act_b.original_duration_days,
                    remaining_duration_delta_days=act_b.remaining_duration_days,
                    total_float_after=cpm_act_b.total_float_days if cpm_act_b else None,
                    status_after=act_b.status,
                    constraint_type_after=act_b.cstr_type,
                    constraint_date_after=act_b.cstr_date,
                    early_finish_after=cpm_act_b.early_finish if cpm_act_b else None,
                )
            )
            added_acts += 1

        else:
            act_a = code_to_act_a[code]
            act_b = code_to_act_b[code]
            cpm_act_a = cpm_a.activities.get(act_a.task_id)
            cpm_act_b = cpm_b.activities.get(act_b.task_id)

            dur_delta = act_b.original_duration_days - act_a.original_duration_days
            rem_dur_delta = act_b.remaining_duration_days - act_a.remaining_duration_days
            tf_a = cpm_act_a.total_float_days if cpm_act_a else None
            tf_b = cpm_act_b.total_float_days if cpm_act_b else None
            tf_delta = (tf_b - tf_a) if (tf_a is not None and tf_b is not None) else None

            ef_a = cpm_act_a.early_finish if cpm_act_a else None
            ef_b = cpm_act_b.early_finish if cpm_act_b else None
            ef_delta_days = (ef_b - ef_a).total_seconds() / 86400.0 if (ef_a and ef_b) else 0.0

            has_changed = (
                abs(dur_delta) > 1e-4
                or abs(rem_dur_delta) > 1e-4
                or act_a.status != act_b.status
                or act_a.cstr_type != act_b.cstr_type
                or act_a.cstr_date != act_b.cstr_date
                or (tf_delta is not None and abs(tf_delta) > 1e-4)
            )

            if has_changed:
                activity_diffs.append(
                    ActivityDiff(
                        task_code=code,
                        name_before=getattr(act_a, "name", None) or act_a.task_code,
                        name_after=getattr(act_b, "name", None) or act_b.task_code,
                        change_type="MODIFIED",
                        duration_delta_days=dur_delta,
                        remaining_duration_delta_days=rem_dur_delta,
                        total_float_before=tf_a,
                        total_float_after=tf_b,
                        total_float_delta_days=tf_delta,
                        status_before=act_a.status,
                        status_after=act_b.status,
                        constraint_type_before=act_a.cstr_type,
                        constraint_type_after=act_b.cstr_type,
                        constraint_date_before=act_a.cstr_date,
                        constraint_date_after=act_b.cstr_date,
                        early_finish_before=ef_a,
                        early_finish_after=ef_b,
                        early_finish_delta_days=ef_delta_days,
                    )
                )
                modified_acts += 1

    # 3. Map relationships by stable relationship_key (pred_code__succ_code__type)
    tid_to_code_a = {act.task_id: act.task_code for act in acts_a.values()}
    tid_to_code_b = {act.task_id: act.task_code for act in acts_b.values()}

    rel_map_a: Dict[str, Tuple[str, str, str, CPMRelationshipInput]] = {}
    for r in rels_a:
        p_code = tid_to_code_a.get(r.pred_task_id)
        s_code = tid_to_code_a.get(r.succ_task_id)
        if p_code and s_code:
            key = generate_relationship_key(p_code, s_code, r.rel_type)
            rel_map_a[key] = (p_code, s_code, r.rel_type, r)

    rel_map_b: Dict[str, Tuple[str, str, str, CPMRelationshipInput]] = {}
    for r in rels_b:
        p_code = tid_to_code_b.get(r.pred_task_id)
        s_code = tid_to_code_b.get(r.succ_task_id)
        if p_code and s_code:
            key = generate_relationship_key(p_code, s_code, r.rel_type)
            rel_map_b[key] = (p_code, s_code, r.rel_type, r)

    all_rel_keys = set(rel_map_a.keys()).union(set(rel_map_b.keys()))
    relationship_diffs: List[RelationshipDiff] = []
    added_rels = 0
    removed_rels = 0
    modified_rels = 0

    for key in sorted(all_rel_keys):
        in_a = key in rel_map_a
        in_b = key in rel_map_b

        if in_a and not in_b:
            p_code, s_code, r_type, r_a = rel_map_a[key]
            relationship_diffs.append(
                RelationshipDiff(
                    relationship_key=key,
                    pred_task_code=p_code,
                    succ_task_code=s_code,
                    change_type="REMOVED",
                    rel_type_before=r_a.rel_type,
                    lag_before=r_a.lag_days,
                    lag_delta_days=-r_a.lag_days,
                )
            )
            removed_rels += 1

        elif in_b and not in_a:
            p_code, s_code, r_type, r_b = rel_map_b[key]
            relationship_diffs.append(
                RelationshipDiff(
                    relationship_key=key,
                    pred_task_code=p_code,
                    succ_task_code=s_code,
                    change_type="ADDED",
                    rel_type_after=r_b.rel_type,
                    lag_after=r_b.lag_days,
                    lag_delta_days=r_b.lag_days,
                )
            )
            added_rels += 1

        else:
            p_code, s_code, r_type, r_a = rel_map_a[key]
            _, _, _, r_b = rel_map_b[key]
            lag_delta = r_b.lag_days - r_a.lag_days
            if abs(lag_delta) > 1e-4:
                relationship_diffs.append(
                    RelationshipDiff(
                        relationship_key=key,
                        pred_task_code=p_code,
                        succ_task_code=s_code,
                        change_type="MODIFIED",
                        rel_type_before=r_a.rel_type,
                        rel_type_after=r_b.rel_type,
                        lag_before=r_a.lag_days,
                        lag_after=r_b.lag_days,
                        lag_delta_days=lag_delta,
                    )
                )
                modified_rels += 1

    # 4. Driver Churn Analysis (Reusing Phase 1 discrete driver detection)
    drivers_a = detect_negative_float_drivers(cpm_a, acts_a, rels_a)
    drivers_b = detect_negative_float_drivers(cpm_b, acts_b, rels_b)

    driver_codes_a = {dh.driver_task_code for dh in drivers_a.drivers}
    driver_codes_b = {dh.driver_task_code for dh in drivers_b.drivers}

    # Map driver task codes to DrivingChainTree objects
    dh_map_a = {dh.driver_task_code: dh for dh in drivers_a.drivers}
    dh_map_b = {dh.driver_task_code: dh for dh in drivers_b.drivers}

    new_drivers = sorted(list(driver_codes_b - driver_codes_a))
    resolved_drivers = sorted(list(driver_codes_a - driver_codes_b))
    persistent_drivers = sorted(list(driver_codes_a.intersection(driver_codes_b)))

    persistent_float_deltas: Dict[str, float] = {}
    for code in persistent_drivers:
        tf_a = dh_map_a[code].driver_total_float_days
        tf_b = dh_map_b[code].driver_total_float_days
        persistent_float_deltas[code] = round(tf_b - tf_a, 2)

    driver_churn = DriverChurn(
        new_drivers=new_drivers,
        resolved_drivers=resolved_drivers,
        persistent_drivers=persistent_drivers,
        persistent_driver_float_deltas=persistent_float_deltas,
    )

    # 5. Project-level Finish Date Comparison
    proj_finish_a = cpm_a.project_early_finish
    proj_finish_b = cpm_b.project_early_finish
    proj_slippage = (proj_finish_b - proj_finish_a).total_seconds() / 86400.0 if (proj_finish_a and proj_finish_b) else 0.0

    return SnapshotDiffResult(
        snapshot_a_id=snapshot_a_id,
        snapshot_b_id=snapshot_b_id,
        snapshot_a_data_date=options_a.data_date,
        snapshot_b_data_date=options_b.data_date,
        total_activities_a=len(acts_a),
        total_activities_b=len(acts_b),
        added_activities_count=added_acts,
        removed_activities_count=removed_acts,
        modified_activities_count=modified_acts,
        total_relationships_a=len(rels_a),
        total_relationships_b=len(rels_b),
        added_relationships_count=added_rels,
        removed_relationships_count=removed_rels,
        modified_relationships_count=modified_rels,
        activity_diffs=activity_diffs,
        relationship_diffs=relationship_diffs,
        driver_churn=driver_churn,
        discrete_delayed_count_a=drivers_a.total_negative_float_activities,
        discrete_delayed_count_b=drivers_b.total_negative_float_activities,
        discrete_delayed_net_delta=drivers_b.total_negative_float_activities - drivers_a.total_negative_float_activities,
        project_finish_date_a=proj_finish_a,
        project_finish_date_b=proj_finish_b,
        project_finish_slippage_days=proj_slippage,
    )
