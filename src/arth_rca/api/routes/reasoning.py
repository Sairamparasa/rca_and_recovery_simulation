"""
FastAPI REST routes for AI Reasoning, Grounded Reporting, and Natural Language Queries.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from arth_rca.db.database import get_db
from arth_rca.db.models import Snapshot, Activity, Relationship, Project, Scenario
from arth_rca.reasoning.types import (
    NLQueryRequest,
    NLQueryResponse,
    NarrativeReportPayload,
    ScenarioExplanationPayload,
)
from arth_rca.reasoning.nl_query import execute_nl_query
from arth_rca.reasoning.report_generator import generate_grounded_narrative_report
from arth_rca.reasoning.recommendations import explain_single_scenario
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.dcma import run_dcma_14_point_assessment

router = APIRouter(prefix="/api/v1", tags=["Reasoning & NL Query"])


@router.post("/query", response_model=NLQueryResponse)
def query_natural_language(
    request: NLQueryRequest,
    db: Session = Depends(get_db),
):
    """
    Executes a natural language query against schedule, driver, DCMA, or trend data,
    and returns a grounded answer with citations and certainty tiers.
    """
    return execute_nl_query(request=request, db=db)


@router.get("/snapshots/{snapshot_id}/report", response_model=NarrativeReportPayload)
def get_snapshot_narrative_report(
    snapshot_id: int,
    db: Session = Depends(get_db),
):
    """
    Generates a full executive narrative report for the given snapshot,
    grounded strictly against computed driver diagnostics and DCMA health metrics.
    """
    snap = db.query(Snapshot).filter(Snapshot.id == snapshot_id).first()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    proj = db.query(Project).filter(Project.id == snap.project_id).first()
    proj_name = proj.name if proj else "Project"

    # Build CPM and driver analysis
    tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
    rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()

    acts_map = {
        t.id: CPMActivityInput(
            task_id=t.id,
            task_code=t.task_code,
            calendar_id=t.calendar_id or 1,
            original_duration_days=t.original_duration,
            remaining_duration_days=t.remaining_duration,
            status=t.status,
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
    cals_map = {
        1: CPMCalendarInput(
            clndr_id=1,
            name="Standard 5-Day",
            working_days=[True, True, True, True, True, False, False],
            work_hours_per_day=8.0,
            holidays=[],
            work_exceptions={},
        )
    }

    cpm_res = run_cpm(acts_map, rels_input, cals_map, CPMOptions(data_date=snap.data_date))
    driver_res = detect_negative_float_drivers(cpm_res, acts_map, rels_input, snapshot_id=snap.id)

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

    raw_tasks_dict = {tid: TaskWrapper(act) for tid, act in acts_map.items()}
    dcma_res = run_dcma_14_point_assessment(
        cpm_result=cpm_res,
        raw_tasks=raw_tasks_dict,
        raw_relationships=rels_input,
        data_date=snap.data_date,
        snapshot_id=snap.id,
    )

    return generate_grounded_narrative_report(
        snapshot_id=snap.id,
        data_date=snap.data_date,
        project_name=proj_name,
        driver_result=driver_res,
        dcma_report=dcma_res,
    )


@router.post("/scenarios/{scenario_id}/explain", response_model=ScenarioExplanationPayload)
def explain_scenario_endpoint(
    scenario_id: int,
    db: Session = Depends(get_db),
):
    """
    Provides a grounded qualitative explanation of a specific what-if scenario.
    """
    scen = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scen:
        raise HTTPException(status_code=404, detail="Scenario not found")

    finish_date_str = scen.result_finish_date.strftime("%Y-%m-%d") if scen.result_finish_date else None
    levers = scen.levers_applied_json or []

    return explain_single_scenario(
        scenario_id=scen.id,
        cost_delta=scen.result_cost_delta or 0.0,
        days_recovered=0.0,  # can be derived from baseline delta
        project_finish_date=finish_date_str,
        critical_path_shift=True,
        levers_applied=levers,
    )
