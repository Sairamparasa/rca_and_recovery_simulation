from pathlib import Path
from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data

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
cpm_res2 = run_cpm(acts2, rels2, cals2, options2, project_data_dates=proj_data_dates2, project_late_anchors=proj_late_anchors2)

cp_acts2 = [acts2[tid] for tid, r in cpm_res2.activities.items() if r.is_critical and acts2[tid].remaining_duration_days > 0 and acts2[tid].status != 'COMPLETED' and acts2[tid].task_type not in ('TT_LOE', 'TT_WBS')]
print(f"File 2 uncompleted critical path activities count: {len(cp_acts2)}")
for a in cp_acts2[:10]:
    print(f"  - {a.task_code}: Dur={a.remaining_duration_days}d (TF={cpm_res2.activities[a.task_id].total_float_days}d, EF={cpm_res2.activities[a.task_id].early_finish})")
