"""
Analytics API routes for Phase 1:
- Driver identification & blast-radius tree queries
- Deterministic root-cause analysis
- Configurable impact scoring configuration
- DCMA 14-point schedule health assessments
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from pydantic import BaseModel

from arth_rca.db.database import get_db
from arth_rca.analytics.driver_detection import detect_negative_float_drivers, DriverAnalysisResult
from arth_rca.analytics.root_cause import classify_driver_root_cause
from arth_rca.analytics.impact_scoring import calculate_driver_impact_score, ScoringConfig
from arth_rca.analytics.dcma import run_dcma_14_point_assessment, DCMAAssessmentReport
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.analytics.snapshot_diff import SnapshotDiffResult, compute_snapshot_diff
from arth_rca.analytics.trend import HistoricalTrendPayload, SnapshotDataPackage, aggregate_historical_trends
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    CalendarModel,
    DCMAHealthCheck,
    DriverRecord,
)

router = APIRouter(prefix="/api/v1", tags=["Analytics & Health Checks"])

# In-memory store fallback for project scoring configuration
_PROJECT_SCORING_CONFIGS: Dict[int, ScoringConfig] = {}


@router.get("/projects/{project_id}/scoring-config", response_model=ScoringConfig)
def get_project_scoring_config(project_id: int, db: Session = Depends(get_db)):
    """Retrieve custom impact scoring configuration for a project."""
    if project_id in _PROJECT_SCORING_CONFIGS:
        return _PROJECT_SCORING_CONFIGS[project_id]
    return ScoringConfig(project_id=project_id)


@router.put("/projects/{project_id}/scoring-config", response_model=ScoringConfig)
def update_project_scoring_config(project_id: int, config: ScoringConfig, db: Session = Depends(get_db)):
    """Update custom impact scoring configuration for a project."""
    config.project_id = project_id
    _PROJECT_SCORING_CONFIGS[project_id] = config
    return config


@router.get("/snapshots/{snapshot_id}/drivers", response_model=DriverAnalysisResult)
def get_snapshot_drivers(snapshot_id: int, db: Session = Depends(get_db)):
    """
    Perform driver identification, deterministic root-cause typing, and forward blast-radius analysis.
    """
    snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    tasks = db.query(Activity).filter(Activity.snapshot_id == snapshot_id).all()
    rels = db.query(Relationship).filter(Relationship.snapshot_id == snapshot_id).all()
    calendars = db.query(CalendarModel).filter(CalendarModel.project_id == snapshot.project_id).all()

    if not tasks:
        return DriverAnalysisResult(
            snapshot_id=snapshot_id,
            total_negative_float_activities=0,
            driver_head_count=0,
            convergence_nodes=[],
            drivers=[],
        )

    # Activity ID lookup
    act_id_to_obj = {t.id: t for t in tasks}

    # Build CPM inputs
    cals_map = {}
    for c in calendars:
        cals_map[c.id] = CPMCalendarInput(
            clndr_id=c.id,
            name=c.name,
            working_days={0, 1, 2, 3, 4},
            work_hours_per_day=8.0,
        )
    if not cals_map:
        cals_map[1] = CPMCalendarInput(clndr_id=1, name="Standard 5 Day", working_days={0, 1, 2, 3, 4})

    acts_map = {
        t.id: CPMActivityInput(
            task_id=t.id,
            task_code=t.task_code,
            calendar_id=t.calendar_id or 1,
            original_duration_days=t.original_duration,
            remaining_duration_days=t.remaining_duration,
            status=t.status,
            act_start_date=t.actual_start,
            act_finish_date=t.actual_finish,
            cstr_type=t.constraint_type,
            cstr_date=t.constraint_date,
            is_milestone=t.is_milestone,
        )
        for t in tasks
    }

    rels_input = [
        CPMRelationshipInput(
            rel_id=r.id or idx,
            pred_task_id=r.predecessor_activity_id,
            succ_task_id=r.successor_activity_id,
            rel_type=r.relationship_type or "FS",
            lag_days=r.lag,
        )
        for idx, r in enumerate(rels, start=1)
    ]

    options = CPMOptions(data_date=snapshot.data_date)
    cpm_result = run_cpm(acts_map, rels_input, cals_map, options)

    # Mock/wrap tasks for analytics
    class TaskWrapper:
        def __init__(self, act: Activity):
            self.task_id = act.id
            self.task_code = act.task_code
            self.status_code = "TK_Complete" if act.status == "COMPLETED" else ("TK_Active" if act.status == "IN_PROGRESS" else "TK_NotStart")
            self.task_type = "TT_FinMile" if act.is_milestone else "TT_Task"
            self.cstr_type = act.constraint_type
            self.cstr_date = act.constraint_date
            self.target_durn_hr_cnt = act.original_duration * 8.0

    raw_tasks_dict = {t.id: TaskWrapper(t) for t in tasks}
    analysis = detect_negative_float_drivers(cpm_result, raw_tasks_dict, rels_input, snapshot_id=snapshot_id)

    # Load scoring configuration
    score_cfg = get_project_scoring_config(snapshot.project_id, db)

    # Decorate driver trees with root-cause typing and impact scores
    for driver in analysis.drivers:
        driver_raw = raw_tasks_dict.get(driver.driver_task_id)
        driver_cpm = cpm_result.activities.get(driver.driver_task_id)
        driver_preds = [r for r in rels_input if r.succ_task_id == driver.driver_task_id]

        rc_res = classify_driver_root_cause(
            driver_task_id=driver.driver_task_id,
            raw_task=driver_raw,
            cpm_act_result=driver_cpm,
            predecessors=driver_preds,
            all_raw_tasks=raw_tasks_dict,
        )
        driver.root_cause_type = rc_res.category
        driver.root_cause_description = rc_res.summary

        driver.impact_score = calculate_driver_impact_score(
            downstream_activity_count=driver.downstream_activity_count,
            total_float_days=driver.driver_total_float_days,
            milestone_count=driver.milestone_count,
            config=score_cfg,
        )

    # Rank drivers descending by impact score
    analysis.drivers.sort(key=lambda d: d.impact_score, reverse=True)
    return analysis


@router.get("/snapshots/{snapshot_id}/dcma", response_model=DCMAAssessmentReport)
def get_snapshot_dcma_assessment(snapshot_id: int, db: Session = Depends(get_db)):
    """
    Run the complete DCMA 14-point schedule health assessment on the schedule snapshot.
    """
    snapshot = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    tasks = db.query(Activity).filter(Activity.snapshot_id == snapshot_id).all()
    rels = db.query(Relationship).filter(Relationship.snapshot_id == snapshot_id).all()
    calendars = db.query(CalendarModel).filter(CalendarModel.project_id == snapshot.project_id).all()

    cals_map = {}
    for c in calendars:
        cals_map[c.id] = CPMCalendarInput(
            clndr_id=c.id,
            name=c.name,
            working_days={0, 1, 2, 3, 4},
            work_hours_per_day=8.0,
        )
    if not cals_map:
        cals_map[1] = CPMCalendarInput(clndr_id=1, name="Standard 5 Day", working_days={0, 1, 2, 3, 4})

    acts_map = {
        t.id: CPMActivityInput(
            task_id=t.id,
            task_code=t.task_code,
            calendar_id=t.calendar_id or 1,
            original_duration_days=t.original_duration,
            remaining_duration_days=t.remaining_duration,
            status=t.status,
            act_start_date=t.actual_start,
            act_finish_date=t.actual_finish,
            cstr_type=t.constraint_type,
            cstr_date=t.constraint_date,
            is_milestone=t.is_milestone,
        )
        for t in tasks
    }

    rels_input = [
        CPMRelationshipInput(
            rel_id=r.id or idx,
            pred_task_id=r.predecessor_activity_id,
            succ_task_id=r.successor_activity_id,
            rel_type=r.relationship_type or "FS",
            lag_days=r.lag,
        )
        for idx, r in enumerate(rels, start=1)
    ]

    options = CPMOptions(data_date=snapshot.data_date)
    cpm_result = run_cpm(acts_map, rels_input, cals_map, options)

    class TaskWrapper:
        def __init__(self, act: Activity):
            self.task_id = act.id
            self.task_code = act.task_code
            self.status_code = "TK_Complete" if act.status == "COMPLETED" else ("TK_Active" if act.status == "IN_PROGRESS" else "TK_NotStart")
            self.task_type = "TT_FinMile" if act.is_milestone else "TT_Task"
            self.cstr_type = act.constraint_type
            self.cstr_date = act.constraint_date
            self.target_durn_hr_cnt = act.original_duration * 8.0
            self.act_start_date = act.actual_start
            self.act_end_date = act.actual_finish

    raw_tasks_dict = {t.id: TaskWrapper(t) for t in tasks}

    report = run_dcma_14_point_assessment(
        cpm_result=cpm_result,
        raw_tasks=raw_tasks_dict,
        raw_relationships=rels_input,
        data_date=snapshot.data_date,
        snapshot_id=snapshot_id,
    )
    return report


@router.get("/snapshots/{snapshot_id}/diff", response_model=SnapshotDiffResult)
def get_snapshot_diff(
    snapshot_id: int,
    compare_to_snapshot_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Compare snapshot_id against a baseline or previous snapshot.
    If compare_to_snapshot_id is omitted, compares against the project baseline or prior chronological snapshot.
    """
    snap_b = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snap_b:
        raise HTTPException(status_code=404, detail="Target snapshot not found")

    if compare_to_snapshot_id:
        snap_a = db.query(Snapshot).filter(Snapshot.id == compare_to_snapshot_id).first()
    else:
        # Default to baseline of same project, or previous chronological snapshot
        snap_a = db.query(Snapshot).filter(Snapshot.project_id == snap_b.project_id, Snapshot.is_baseline == True).first()
        if not snap_a or snap_a.id == snap_b.id:
            snap_a = (
                db.query(Snapshot)
                .filter(Snapshot.project_id == snap_b.project_id, Snapshot.data_date < snap_b.data_date)
                .order_by(Snapshot.data_date.desc())
                .first()
            )

    if not snap_a:
        raise HTTPException(status_code=400, detail="No comparison baseline or prior snapshot found for project")

    def build_inputs(snap: Snapshot):
        cals = db.query(CalendarModel).filter(CalendarModel.project_id == snap.project_id).all()
        cals_map = {}
        for c in cals:
            clndr_raw = getattr(c, "clndr_data", "")
            if clndr_raw:
                wd, hol, wex = parse_p6_clndr_data(clndr_raw)
            else:
                wd = [True, True, True, True, True, False, False]
                hol, wex = [], {}
            cals_map[c.id] = CPMCalendarInput(
                clndr_id=c.id,
                name=c.name,
                working_days=wd,
                work_hours_per_day=getattr(c, "day_hr_cnt", 8.0) or 8.0,
                holidays=hol,
                work_exceptions=wex,
            )

        tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
        acts_map = {
            t.id: CPMActivityInput(
                task_id=t.id,
                task_code=t.task_code,
                calendar_id=t.calendar_id or 1,
                original_duration_days=t.original_duration,
                remaining_duration_days=t.remaining_duration,
                status=t.status,
                act_start_date=t.actual_start,
                act_finish_date=t.actual_finish,
                cstr_type=t.constraint_type,
                cstr_date=t.constraint_date,
                is_milestone=t.is_milestone,
            )
            for t in tasks
        }

        rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()
        rels_input = [
            CPMRelationshipInput(
                rel_id=r.id or idx,
                pred_task_id=r.predecessor_activity_id,
                succ_task_id=r.successor_activity_id,
                rel_type=r.relationship_type or "FS",
                lag_days=r.lag,
            )
            for idx, r in enumerate(rels, start=1)
        ]
        options = CPMOptions(data_date=snap.data_date)
        return acts_map, rels_input, cals_map, options

    acts_a, rels_a, cals_a, opts_a = build_inputs(snap_a)
    acts_b, rels_b, cals_b, opts_b = build_inputs(snap_b)

    return compute_snapshot_diff(
        acts_a=acts_a,
        rels_a=rels_a,
        cals_a=cals_a,
        options_a=opts_a,
        acts_b=acts_b,
        rels_b=rels_b,
        cals_b=cals_b,
        options_b=opts_b,
        snapshot_a_id=snap_a.id,
        snapshot_b_id=snap_b.id,
    )


@router.get("/projects/{project_id}/trend", response_model=HistoricalTrendPayload)
def get_project_historical_trend(
    project_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieve historical trend data across all ingested snapshots for a project.
    Strictly historical facts and point-to-point calculations (zero extrapolation).
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    snapshots = db.query(Snapshot).filter(Snapshot.project_id == project_id).order_by(Snapshot.data_date.asc()).all()
    if not snapshots:
        return HistoricalTrendPayload(project_id=project_id, total_snapshots=0)

    packages: List[SnapshotDataPackage] = []
    cals = db.query(CalendarModel).filter(CalendarModel.project_id == project_id).all()
    cals_map = {}
    for c in cals:
        clndr_raw = getattr(c, "clndr_data", "")
        if clndr_raw:
            wd, hol, wex = parse_p6_clndr_data(clndr_raw)
        else:
            wd = [True, True, True, True, True, False, False]
            hol, wex = [], {}
        cals_map[c.id] = CPMCalendarInput(
            clndr_id=c.id,
            name=c.name,
            working_days=wd,
            work_hours_per_day=getattr(c, "day_hr_cnt", 8.0) or 8.0,
            holidays=hol,
            work_exceptions=wex,
        )

    for snap in snapshots:
        tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
        acts_map = {
            t.id: CPMActivityInput(
                task_id=t.id,
                task_code=t.task_code,
                calendar_id=t.calendar_id or 1,
                original_duration_days=t.original_duration,
                remaining_duration_days=t.remaining_duration,
                status=t.status,
                act_start_date=t.actual_start,
                act_finish_date=t.actual_finish,
                cstr_type=t.constraint_type,
                cstr_date=t.constraint_date,
                is_milestone=t.is_milestone,
            )
            for t in tasks
        }

        rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()
        rels_input = [
            CPMRelationshipInput(
                rel_id=r.id or idx,
                pred_task_id=r.predecessor_activity_id,
                succ_task_id=r.successor_activity_id,
                rel_type=r.relationship_type or "FS",
                lag_days=r.lag,
            )
            for idx, r in enumerate(rels, start=1)
        ]
        options = CPMOptions(data_date=snap.data_date)

        packages.append(
            SnapshotDataPackage(
                snapshot_id=snap.id,
                data_date=snap.data_date,
                is_baseline=snap.is_baseline,
                source_filename=snap.source_filename,
                activities=acts_map,
                relationships=rels_input,
                calendars=cals_map,
                options=options,
            )
        )

    return aggregate_historical_trends(project_id=project_id, snapshots=packages)

