"""
Run real schedule optimization on PHX3DC1 and 247011 top drivers.
Generates full Pareto frontiers trading off recovery costs vs days recovered and discrete delayed count.
"""

from pathlib import Path
from datetime import datetime

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.classification import classify_relationship
from arth_rca.db.models import generate_relationship_key, RelationshipClassification
from arth_rca.optimization.optimizer import optimize_schedule_recovery, generate_candidate_levers_for_drivers
from arth_rca.optimization.config import OptimizationConfig

# ==============================================================================
# 1. OPTIMIZATION ON FILE 1: PHX3DC1 (Phoenix Baseline)
# ==============================================================================
p1 = XERParser().parse_file(Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer'))
proj1 = next(iter(p1.projects.values()))
proj_data_dates1 = {pid: pr.last_recalc_date for pid, pr in p1.projects.items()}
proj_late_anchors1 = {pid: pr.must_finish_by_date for pid, pr in p1.projects.items() if pr.must_finish_by_date}

cals1 = {}
for cid, c in p1.calendars.items():
    wd, hol, wex = parse_p6_clndr_data(c.clndr_data or '')
    cals1[cid] = CPMCalendarInput(clndr_id=cid, name=c.clndr_name, working_days=wd, work_hours_per_day=c.day_hr_cnt, holidays=hol, work_exceptions=wex)

acts1 = {
    tid: CPMActivityInput(
        task_id=t.task_id, task_code=t.task_code, calendar_id=t.clndr_id or 1, proj_id=t.proj_id,
        original_duration_days=t.target_durn_hr_cnt / 8.0, remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
        status='COMPLETED' if t.status_code == 'TK_Complete' else ('IN_PROGRESS' if t.status_code == 'TK_Active' else 'NOT_STARTED'),
        act_start_date=t.act_start_date, act_finish_date=t.act_end_date,
        cstr_type=t.cstr_type, cstr_date=t.cstr_date, is_milestone='Mile' in t.task_type,
        task_type=t.task_type,
    )
    for tid, t in p1.tasks.items()
}

rels1 = [
    CPMRelationshipInput(
        rel_id=pr.task_pred_id, pred_task_id=pr.pred_task_id, succ_task_id=pr.task_id,
        rel_type='FS' if pr.pred_type == 'PR_FS' else ('SS' if pr.pred_type == 'PR_SS' else ('FF' if pr.pred_type == 'PR_FF' else 'SF')),
        lag_days=pr.lag_hr_cnt / 8.0,
    )
    for pr in p1.predecessors
]

options1 = CPMOptions(data_date=proj1.last_recalc_date)

# Classify relationships
class_map1 = {}
for r in rels1:
    pt = acts1.get(r.pred_task_id)
    st = acts1.get(r.succ_task_id)
    if not pt or not st:
        continue
    c_res = classify_relationship(pt.task_code, p1.tasks[r.pred_task_id].task_name or '', st.task_code, p1.tasks[r.succ_task_id].task_name or '', rel_type=r.rel_type, lag_days=r.lag_days)
    class_map1[c_res.relationship_key] = RelationshipClassification(
        relationship_key=c_res.relationship_key,
        project_id=proj1.proj_id,
        constraint_type=c_res.constraint_type,
        confidence=c_res.confidence,
        classification_source=c_res.classification_source,
    )

# Top real drivers from Phase 1 & terminal critical drivers
top_drivers1 = {"QTS-41811", "QTS-29341", "QTS-29711", "QTS-30141", "DC1-MECH-L4-Cx-1070", "DC1-MECH-L4-Cx-1060"}

opt_res1 = optimize_schedule_recovery(
    activities=acts1,
    relationships=rels1,
    calendars=cals1,
    options=options1,
    classifications=class_map1,
    budget_limit=75000.0,
    project_id=proj1.proj_id,
    snapshot_id=1,
    target_driver_task_codes=top_drivers1,
    strategy="AUTO",
    project_data_dates=proj_data_dates1,
    project_late_anchors=proj_late_anchors1,
)

print("================================================================================")
print(f"FILE 1 (PHX3DC1) OPTIMIZATION RESULTS ({opt_res1.solver_used})")
print("================================================================================")
print(f"Budget Limit:              ${opt_res1.budget_limit:,.0f}")
print(f"Total Scenarios Evaluated: {opt_res1.total_scenarios_evaluated}")
print(f"Infeasible Rejected:       {opt_res1.total_infeasible_rejected}")
print(f"Execution Time:            {opt_res1.execution_time_ms:.1f} ms")
print(f"Pareto Frontier Size:      {len(opt_res1.pareto_frontier)} points\n")

print(f"{'Point':<6} | {'Cost ($)':<10} | {'Days Rec':<9} | {'Finish Date':<19} | {'Delayed Acts':<12} | {'CP Shift':<8} | {'Levers'}")
print("-" * 100)
for idx, pt in enumerate(opt_res1.pareto_frontier, 1):
    levers_str = ", ".join([f"{lev['type']}:{lev['target']}" for lev in pt.levers_applied[:3]])
    if len(pt.levers_applied) > 3:
        levers_str += f" (+{len(pt.levers_applied)-3} more)"
    if not pt.levers_applied:
        levers_str = "None (Baseline)"
    print(f"{idx:<6} | ${pt.cost_delta:<9,.0f} | {pt.days_recovered:<9.1f} | {pt.simulated_finish_date:<19} | {pt.remaining_discrete_delayed_count:<12} | {str(pt.critical_path_shifted):<8} | {levers_str}")


# ==============================================================================
# 2. OPTIMIZATION ON FILE 2: 247011 (Large Data Center Update)
# ==============================================================================
p2 = XERParser().parse_file(Path('xer_files/247011 08-18 (1).xer'))
proj2 = next(iter(p2.projects.values()))
proj_data_dates2 = {pid: pr.last_recalc_date for pid, pr in p2.projects.items()}
proj_late_anchors2 = {pid: pr.must_finish_by_date for pid, pr in p2.projects.items() if pr.must_finish_by_date}

cals2 = {}
for cid, c in p2.calendars.items():
    wd, hol, wex = parse_p6_clndr_data(c.clndr_data or '')
    cals2[cid] = CPMCalendarInput(clndr_id=cid, name=c.clndr_name, working_days=wd, work_hours_per_day=c.day_hr_cnt, holidays=hol, work_exceptions=wex)

acts2 = {
    tid: CPMActivityInput(
        task_id=t.task_id, task_code=t.task_code, calendar_id=t.clndr_id or 1, proj_id=t.proj_id,
        original_duration_days=t.target_durn_hr_cnt / 8.0, remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
        status='COMPLETED' if t.status_code == 'TK_Complete' else ('IN_PROGRESS' if t.status_code == 'TK_Active' else 'NOT_STARTED'),
        act_start_date=t.act_start_date, act_finish_date=t.act_end_date,
        cstr_type=t.cstr_type, cstr_date=t.cstr_date, is_milestone='Mile' in t.task_type,
        task_type=t.task_type,
    )
    for tid, t in p2.tasks.items()
}

rels2 = [
    CPMRelationshipInput(
        rel_id=pr.task_pred_id, pred_task_id=pr.pred_task_id, succ_task_id=pr.task_id,
        rel_type='FS' if pr.pred_type == 'PR_FS' else ('SS' if pr.pred_type == 'PR_SS' else ('FF' if pr.pred_type == 'PR_FF' else 'SF')),
        lag_days=pr.lag_hr_cnt / 8.0,
    )
    for pr in p2.predecessors
]

options2 = CPMOptions(data_date=proj2.last_recalc_date)

top_drivers2 = {"QTS-28981", "QTS-29481", "QTS-29491", "QTS-29661", "QTS-29751"}

opt_res2 = optimize_schedule_recovery(
    activities=acts2,
    relationships=rels2,
    calendars=cals2,
    options=options2,
    classifications={},
    budget_limit=150000.0,
    project_id=proj2.proj_id,
    snapshot_id=2,
    target_driver_task_codes=top_drivers2,
    strategy="AUTO",
    project_data_dates=proj_data_dates2,
    project_late_anchors=proj_late_anchors2,
)

print("\n================================================================================")
print(f"FILE 2 (247011) OPTIMIZATION RESULTS ({opt_res2.solver_used})")
print("================================================================================")
print(f"Budget Limit:              ${opt_res2.budget_limit:,.0f}")
print(f"Total Scenarios Evaluated: {opt_res2.total_scenarios_evaluated}")
print(f"Infeasible Rejected:       {opt_res2.total_infeasible_rejected}")
print(f"Execution Time:            {opt_res2.execution_time_ms:.1f} ms")
print(f"Pareto Frontier Size:      {len(opt_res2.pareto_frontier)} points\n")

print(f"{'Point':<6} | {'Cost ($)':<10} | {'Days Rec':<9} | {'Finish Date':<19} | {'Delayed Acts':<12} | {'CP Shift':<8} | {'Levers'}")
print("-" * 100)
for idx, pt in enumerate(opt_res2.pareto_frontier, 1):
    levers_str = ", ".join([f"{lev['type']}:{lev['target']}" for lev in pt.levers_applied[:3]])
    if len(pt.levers_applied) > 3:
        levers_str += f" (+{len(pt.levers_applied)-3} more)"
    if not pt.levers_applied:
        levers_str = "None (Baseline)"
    print(f"{idx:<6} | ${pt.cost_delta:<9,.0f} | {pt.days_recovered:<9.1f} | {pt.simulated_finish_date:<19} | {pt.remaining_discrete_delayed_count:<12} | {str(pt.critical_path_shifted):<8} | {levers_str}")
