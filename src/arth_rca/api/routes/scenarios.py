"""
FastAPI REST routes for Phase 3: What-If Recovery Simulation & Scenario Comparison.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime

from arth_rca.db.database import get_db
from arth_rca.db.models import (
    Project,
    Snapshot,
    Activity,
    Relationship,
    CalendarModel,
    RelationshipClassification,
    Scenario,
    utc_now,
)
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.simulation.engine import run_simulation, SimulationDiffResult
from arth_rca.simulation.levers import (
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
)

router = APIRouter(prefix="/api/v1", tags=["Recovery Simulation & Scenarios"])


class RunScenarioRequest(BaseModel):
    project_id: int
    baseline_snapshot_id: int
    name: str = "Recovery Scenario"
    description: Optional[str] = None
    created_by: str = "PM_USER"
    levers: List[Dict[str, Any]]
    scoped_preview: bool = False


class ScenarioComparisonItem(BaseModel):
    scenario_id: int
    name: str
    created_by: Optional[str]
    created_at: datetime
    status: str
    result_finish_date: Optional[datetime]
    days_recovered: float
    remaining_discrete_delayed: int
    cost_delta: float
    levers_count: int
    requires_pm_approval: bool


def _parse_lever_payload(lever_dict: Dict[str, Any]) -> Any:
    """Parse raw json dictionary into typed Lever model."""
    ltype = lever_dict.get("lever_type", "").upper()
    if ltype == "CRASH":
        return CrashLever(**lever_dict)
    elif ltype == "FAST_TRACK":
        return FastTrackLever(**lever_dict)
    elif ltype == "LOGIC_CHANGE":
        return LogicChangeLever(**lever_dict)
    elif ltype == "CONSTRAINT_RELAXATION":
        return ConstraintRelaxationLever(**lever_dict)
    elif ltype == "RESEQUENCING":
        return ResequencingLever(**lever_dict)
    elif ltype == "CALENDAR_CHANGE":
        return CalendarChangeLever(**lever_dict)
    elif ltype == "ACTIVITY_SPLIT":
        return ActivitySplitLever(**lever_dict)
    else:
        raise ValueError(f"Unknown lever_type: '{ltype}'")


@router.post("/scenarios", response_model=SimulationDiffResult)
def create_and_run_scenario(
    req: RunScenarioRequest,
    db: Session = Depends(get_db),
):
    """
    Execute a recovery simulation scenario on a snapshot, applying levers onto a cloned graph,
    validating safety gates, running the CPM engine, saving the scenario, and returning diffs.
    """
    snap = db.query(Snapshot).filter(
        Snapshot.id == req.baseline_snapshot_id,
        Snapshot.project_id == req.project_id,
    ).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Baseline snapshot not found")

    tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
    rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()
    cals = db.query(CalendarModel).filter(CalendarModel.project_id == snap.project_id).all()
    classifications = {
        r.relationship_key: r for r in db.query(RelationshipClassification).filter(RelationshipClassification.project_id == req.project_id).all()
    }

    # Parse typed levers
    typed_levers = []
    for l_dict in req.levers:
        try:
            typed_levers.append(_parse_lever_payload(l_dict))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Construct CPM structures
    cpm_cals: Dict[int, CPMCalendarInput] = {}
    for c in cals:
        wd, hol, wex = parse_p6_clndr_data(c.working_days_json or "")
        cpm_cals[c.id] = CPMCalendarInput(
            clndr_id=c.id, name=c.name or "Calendar", working_days=wd,
            work_hours_per_day=8.0, holidays=hol, work_exceptions=wex
        )

    cpm_acts: Dict[int, CPMActivityInput] = {
        t.id: CPMActivityInput(
            task_id=t.id,
            task_code=t.task_code,
            calendar_id=t.calendar_id or 1,
            proj_id=snap.project_id,
            original_duration_days=t.original_duration or 0.0,
            remaining_duration_days=t.remaining_duration or 0.0,
            status=t.status or "NOT_STARTED",
            act_start_date=t.early_start if t.status in ("IN_PROGRESS", "COMPLETED") else None,
            act_finish_date=t.early_finish if t.status == "COMPLETED" else None,
            cstr_type=t.constraint_type,
            cstr_date=t.constraint_date,
            is_milestone=t.is_milestone,
        )
        for t in tasks
    }

    cpm_rels = [
        CPMRelationshipInput(
            rel_id=r.id,
            pred_task_id=r.predecessor_activity_id,
            succ_task_id=r.successor_activity_id,
            rel_type=r.relationship_type or "FS",
            lag_days=r.lag,
        )
        for r in rels
    ]

    options = CPMOptions(data_date=snap.data_date or datetime(2026, 9, 1))

    try:
        _, diff = run_simulation(
            activities=cpm_acts,
            relationships=cpm_rels,
            calendars=cpm_cals,
            options=options,
            levers=typed_levers,
            classifications=classifications,
            scenario_name=req.name,
            scoped_preview=req.scoped_preview,
        )
    except SafetyViolationError as e:
        raise HTTPException(status_code=422, detail=f"Safety Gate Violation: {str(e)}")
    except CombinatorialConflictError as e:
        raise HTTPException(status_code=400, detail=f"Combinatorial Conflict: {str(e)}")
    except DependencyViolationError as e:
        raise HTTPException(status_code=400, detail=f"Dependency Violation: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")

    # Store scenario record in database
    sim_finish_dt = datetime.fromisoformat(diff.simulated_finish_date) if diff.simulated_finish_date else None
    scenario_row = Scenario(
        project_id=req.project_id,
        baseline_snapshot_id=req.baseline_snapshot_id,
        created_by=req.created_by,
        created_at=utc_now(),
        levers_applied_json=req.levers,
        status=diff.status,
        result_finish_date=sim_finish_dt,
        result_float_summary_json=diff.dict(),
        result_cost_delta=diff.total_cost_delta,
        engine_version="1.0.0",
    )
    db.add(scenario_row)
    db.commit()
    db.refresh(scenario_row)

    return diff


@router.get("/scenarios/{scenario_id}", response_model=Dict[str, Any])
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    """Retrieve details, applied levers, and diff summary for a stored scenario."""
    scen = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scen:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {
        "id": scen.id,
        "project_id": scen.project_id,
        "baseline_snapshot_id": scen.baseline_snapshot_id,
        "created_by": scen.created_by,
        "created_at": scen.created_at,
        "status": scen.status,
        "result_finish_date": scen.result_finish_date,
        "result_cost_delta": scen.result_cost_delta,
        "levers_applied": scen.levers_applied_json,
        "diff_summary": scen.result_float_summary_json,
    }


@router.get("/projects/{project_id}/scenarios/compare", response_model=List[ScenarioComparisonItem])
def compare_project_scenarios(project_id: int, db: Session = Depends(get_db)):
    """
    Retrieve side-by-side comparison table of all scenarios for a given project.
    """
    scenarios = db.query(Scenario).filter(Scenario.project_id == project_id).order_by(Scenario.created_at.desc()).all()
    results: List[ScenarioComparisonItem] = []

    for s in scenarios:
        summary = s.result_float_summary_json or {}
        results.append(
            ScenarioComparisonItem(
                scenario_id=s.id,
                name=summary.get("scenario_name", f"Scenario #{s.id}"),
                created_by=s.created_by,
                created_at=s.created_at,
                status=s.status,
                result_finish_date=s.result_finish_date,
                days_recovered=summary.get("days_recovered", 0.0),
                remaining_discrete_delayed=summary.get("simulated_discrete_delayed_count", 0),
                cost_delta=s.result_cost_delta or 0.0,
                levers_count=len(s.levers_applied_json or []),
                requires_pm_approval=summary.get("requires_pm_approval", False),
            )
        )

    return results
