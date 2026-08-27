import time
import pulp
from pathlib import Path
from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.analytics.classification import classify_relationship
from arth_rca.db.models import RelationshipClassification
from arth_rca.optimization.optimizer import generate_candidate_levers_for_drivers
from arth_rca.optimization.ilp_solver import filter_safety_cleared_candidates
from arth_rca.simulation.engine import run_simulation, validate_lever_set
from arth_rca.optimization.models import ParetoPoint
from arth_rca.optimization.pareto import dominates, extract_pareto_frontier

# ==============================================================================
# 1. FILE 1 FULL EVALUATION & CANDIDATE BREAKDOWN
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

top_drivers1 = {"QTS-41811", "QTS-29341", "QTS-29711", "QTS-30141", "DC1-MECH-L4-Cx-1070", "DC1-MECH-L4-Cx-1060"}

all_cands1 = generate_candidate_levers_for_drivers(acts1, rels1, class_map1, top_drivers1)
cleared_cands1, rejected_count1 = filter_safety_cleared_candidates(all_cands1, acts1, rels1, class_map1)

print("=== FILE 1: CANDIDATE LEVER POOL BREAKDOWN ===")
print(f"Total Generated Candidates: {len(all_cands1)}")
print(f"Total Cleared Candidates:   {len(cleared_cands1)}")
print(f"Unsafe/Rejected Candidates: {rejected_count1}")
for c in cleared_cands1:
    print(f"  - [{c.lever_type}] {c.candidate_id}: Cost=${c.estimated_cost:,.0f}, Savings={c.estimated_time_savings_days}d")

# Perform Budget Sweep and capture all evaluated points (dominated vs non-dominated)
evaluated_points1 = []
seen_sets = set()

# Baseline
_, diff_base = run_simulation(acts1, rels1, cals1, options1, [], class_map1, project_data_dates=proj_data_dates1, scenario_name="Baseline")
p_base = ParetoPoint(scenario_name="Baseline", cost_delta=0.0, days_recovered=0.0, simulated_finish_date=diff_base.simulated_finish_date, remaining_discrete_delayed_count=diff_base.simulated_discrete_delayed_count, discrete_delayed_recovered_count=0, critical_path_shifted=False, levers_applied=[])
evaluated_points1.append(p_base)

budget_tiers = [5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 50000, 75000]
for b in budget_tiers:
    prob = pulp.LpProblem(f"TCTP_Tier_{b}", pulp.LpMaximize)
    var_map = {c.candidate_id: pulp.LpVariable(f"x_{i}", cat=pulp.LpBinary) for i, c in enumerate(cleared_cands1)}
    prob += pulp.lpSum([(c.estimated_time_savings_days * 1000.0 - c.estimated_cost * 0.001) * var_map[c.candidate_id] for c in cleared_cands1])
    prob += pulp.lpSum([c.estimated_cost * var_map[c.candidate_id] for c in cleared_cands1]) <= b
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    sel = [c for c in cleared_cands1 if pulp.value(var_map[c.candidate_id]) > 0.5]
    if not sel:
        continue
    k = tuple(sorted(c.candidate_id for c in sel))
    if k in seen_sets:
        continue
    seen_sets.add(k)
    
    levs = [c.lever for c in sel]
    tot_cost = sum(c.estimated_cost for c in sel)
    sim, diff = run_simulation(acts1, rels1, cals1, options1, levs, class_map1, project_data_dates=proj_data_dates1, scenario_name=f"ILP Budget ${b:,}")
    
    summary = [{"candidate_id": c.candidate_id, "type": c.lever_type, "target": c.target_entity, "cost": c.estimated_cost} for c in sel]
    evaluated_points1.append(
        ParetoPoint(
            scenario_name=f"ILP Plan (Budget ${b:,})",
            cost_delta=tot_cost,
            days_recovered=diff.days_recovered,
            simulated_finish_date=diff.simulated_finish_date,
            remaining_discrete_delayed_count=diff.simulated_discrete_delayed_count,
            discrete_delayed_recovered_count=diff.discrete_delayed_recovered_count,
            critical_path_shifted=diff.critical_path_shifted,
            levers_applied=summary,
        )
    )

frontier1 = extract_pareto_frontier(evaluated_points1)
frontier_set = {p.scenario_name for p in frontier1}

print("\n=== FILE 1: ALL EVALUATED ILP SCENARIOS (DOMINATED VS PARETO WINNERS) ===")
print(f"{'Status':<14} | {'Scenario':<26} | {'Cost ($)':<9} | {'Days Rec':<9} | {'Delayed':<8} | {'CP Shift':<8} | {'Levers'}")
print("-" * 115)
for pt in evaluated_points1:
    status_str = "[PARETO]" if pt.scenario_name in frontier_set else "[DOMINATED]"
    levers_str = ", ".join([f"{lev['type']}:{lev['target']}" for lev in pt.levers_applied[:2]])
    if len(pt.levers_applied) > 2:
        levers_str += f" (+{len(pt.levers_applied)-2} more)"
    if not pt.levers_applied:
        levers_str = "None (Baseline)"
    print(f"{status_str:<14} | {pt.scenario_name:<26} | ${pt.cost_delta:<8,.0f} | {pt.days_recovered:<9.1f} | {pt.remaining_discrete_delayed_count:<8} | {str(pt.critical_path_shifted):<8} | {levers_str}")
