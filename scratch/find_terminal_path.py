from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.simulation.engine import run_simulation
from arth_rca.simulation.levers import CrashLever
from pathlib import Path

p1 = XERParser().parse_file(Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer'))
proj1 = next(iter(p1.projects.values()))
proj_data_dates1 = {pid: pr.last_recalc_date for pid, pr in p1.projects.items()}

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
cpm_res = run_cpm(acts1, rels1, cals1, options1, project_data_dates=proj_data_dates1)

max_ef = max(r.early_finish for r in cpm_res.activities.values())
terminal_tids = [tid for tid, r in cpm_res.activities.items() if r.early_finish == max_ef]
print(f"Max Early Finish Date: {max_ef}")
print(f"Terminal Tasks at Max EF ({len(terminal_tids)} tasks):")
for tid in terminal_tids:
    t = p1.tasks[tid]
    print(f"  - {t.task_code}: '{t.task_name}', Dur={t.target_durn_hr_cnt/8}d, ID={t.task_id}")
    preds = [pr for pr in p1.predecessors if pr.task_id == t.task_id]
    for pr in preds:
        pt = p1.tasks.get(pr.pred_task_id)
        print(f"      <- Pred: {pt.task_code} - '{pt.task_name}' (Dur={pt.target_durn_hr_cnt/8}d, EF={cpm_res.activities[pt.task_id].early_finish})")
