from pathlib import Path
from datetime import datetime

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.db.models import RelationshipClassification
from arth_rca.optimization.optimizer import optimize_schedule_recovery, generate_candidate_levers_for_drivers
from arth_rca.simulation.levers import CrashLever
from arth_rca.optimization.models import CandidateLeverOption

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

top_drivers2 = ["QTS-28981", "QTS-29481", "QTS-29491", "QTS-29661", "QTS-29751"]
custom_cands = []
for code in top_drivers2:
    tid = [k for k, v in acts2.items() if v.task_code == code][0]
    act = acts2[tid]
    dur = act.remaining_duration_days
    red = round(dur * 0.5, 1)
    cost = red * 2500.0
    custom_cands.append(
        CandidateLeverOption(
            candidate_id=f"CRASH_{code}_{red:.0f}d",
            lever_type="CRASH",
            target_entity=code,
            lever=CrashLever(task_code=code, reduction_days=red, cost_delta=cost, description=f"Crash {code} by {red}d"),
            estimated_cost=cost,
            estimated_time_savings_days=red,
            is_safety_cleared=True,
            cost_source="ASSUMED_HEURISTIC",
        )
    )

opt_res2 = optimize_schedule_recovery(
    activities=acts2,
    relationships=rels2,
    calendars=cals2,
    options=options2,
    classifications={},
    budget_limit=150000.0,
    project_id=proj2.proj_id,
    snapshot_id=2,
    custom_candidates=custom_cands,
    strategy="ILP",
    project_data_dates=proj_data_dates2,
    project_late_anchors=proj_late_anchors2,
)

print("================================================================================")
print(f"FILE 2 (247011) EXACT ILP OPTIMIZATION RESULTS")
print("================================================================================")
print(f"Budget Limit:              ${opt_res2.budget_limit:,.0f}")
print(f"Total Scenarios Evaluated: {opt_res2.total_scenarios_evaluated}")
print(f"Infeasible Rejected:       {opt_res2.total_infeasible_rejected}")
print(f"Execution Time:            {opt_res2.execution_time_ms:.1f} ms")
print(f"Pareto Frontier Size:      {len(opt_res2.pareto_frontier)} points\n")

print(f"{'Point':<6} | {'Cost ($)':<10} | {'Days Rec':<9} | {'Finish Date':<19} | {'Delayed Acts':<12} | {'CP Shift':<8} | {'Levers'}")
print("-" * 110)
for idx, pt in enumerate(opt_res2.pareto_frontier, 1):
    levers_str = ", ".join([f"{lev['type']}:{lev['target']}" for lev in pt.levers_applied[:3]])
    if len(pt.levers_applied) > 3:
        levers_str += f" (+{len(pt.levers_applied)-3} more)"
    if not pt.levers_applied:
        levers_str = "None (Baseline)"
    print(f"{idx:<6} | ${pt.cost_delta:<9,.0f} | {pt.days_recovered:<9.1f} | {pt.simulated_finish_date:<19} | {pt.remaining_discrete_delayed_count:<12} | {str(pt.critical_path_shifted):<8} | {levers_str}")
