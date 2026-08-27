"""
REST API routes for Phase 4: Recovery Scenario Optimization.
"""

from typing import List, Dict, Optional, Any, Set
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from datetime import datetime

from arth_rca.db.database import get_db
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    CalendarModel,
    RelationshipClassification,
    DriverRecord,
    generate_relationship_key,
)
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.optimization.models import OptimizationRequest, OptimizationResult, CandidateLeverOption
from arth_rca.optimization.optimizer import optimize_schedule_recovery

router = APIRouter(prefix="/api/v1", tags=["optimization"])


@router.post("/projects/{project_id}/scenarios/optimize", response_model=OptimizationResult)
def run_optimization_api(
    project_id: int,
    req: OptimizationRequest,
    db: Session = Depends(get_db),
):
    """
    Execute combinatorial recovery optimization to produce the Time-Cost Pareto frontier.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found.")

    snap = db.query(Snapshot).filter(Snapshot.id == req.snapshot_id, Snapshot.project_id == project_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail=f"Snapshot {req.snapshot_id} not found for Project {project_id}.")

    db_acts = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
    db_rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()
    db_cals = db.query(CalendarModel).filter(CalendarModel.project_id == project_id).all()
    db_classes = db.query(RelationshipClassification).filter(RelationshipClassification.project_id == project_id).all()

    class_map = {c.relationship_key: c for c in db_classes}

    cals_input: Dict[int, CPMCalendarInput] = {}
    for c in db_cals:
        wd, hol, wex = parse_p6_clndr_data(c.exceptions_json or "")
        cals_input[c.id] = CPMCalendarInput(
            clndr_id=c.id,
            name=c.name,
            working_days=wd,
            work_hours_per_day=8.0,
            holidays=hol,
            work_exceptions=wex,
        )

    if not cals_input:
        cals_input[1] = CPMCalendarInput(clndr_id=1, name="Standard", working_days=[0, 1, 2, 3, 4], work_hours_per_day=8.0)

    acts_input: Dict[int, CPMActivityInput] = {
        a.id: CPMActivityInput(
            task_id=a.id,
            task_code=a.task_code,
            calendar_id=a.calendar_id or next(iter(cals_input.keys())),
            original_duration_days=a.original_duration,
            remaining_duration_days=a.remaining_duration,
            status=a.status,
            act_start_date=a.early_start if a.status != "NOT_STARTED" else None,
            act_finish_date=a.early_finish if a.status == "COMPLETED" else None,
            cstr_type=a.constraint_type,
            cstr_date=a.constraint_date,
            is_milestone=a.is_milestone,
            task_type="TT_Task" if not a.is_milestone else "TT_Mile",
        )
        for a in db_acts
    }

    rels_input: List[CPMRelationshipInput] = [
        CPMRelationshipInput(
            rel_id=r.id,
            pred_task_id=r.predecessor_activity_id,
            succ_task_id=r.successor_activity_id,
            rel_type=r.relationship_type,
            lag_days=r.lag,
        )
        for r in db_rels
    ]

    options = CPMOptions(data_date=snap.data_date or datetime.utcnow())

    target_task_codes: Optional[Set[str]] = None
    if req.driver_ids:
        driver_records = db.query(DriverRecord).filter(DriverRecord.id.in_(req.driver_ids)).all()
        target_tids = {d.head_activity_id for d in driver_records}
        target_task_codes = {acts_input[tid].task_code for tid in target_tids if tid in acts_input}

    custom_candidates: Optional[List[CandidateLeverOption]] = None
    if req.custom_levers:
        # Wrap custom levers
        custom_candidates = []
        for i, lev in enumerate(req.custom_levers):
            custom_candidates.append(
                CandidateLeverOption(
                    candidate_id=f"CUSTOM_{i+1}",
                    lever_type="CUSTOM",
                    target_entity=getattr(lev, "task_code", getattr(lev, "pred_task_code", "UNKNOWN")),
                    lever=lev,
                    estimated_cost=getattr(lev, "cost_delta", 0.0),
                    estimated_time_savings_days=getattr(lev, "reduction_days", 1.0),
                    is_safety_cleared=True,
                    cost_source="CUSTOM",
                )
            )

    result = optimize_schedule_recovery(
        activities=acts_input,
        relationships=rels_input,
        calendars=cals_input,
        options=options,
        classifications=class_map,
        budget_limit=req.budget_limit,
        project_id=project_id,
        snapshot_id=snap.id,
        target_driver_task_codes=target_task_codes,
        custom_candidates=custom_candidates,
        strategy=req.strategy,
    )

    return result
