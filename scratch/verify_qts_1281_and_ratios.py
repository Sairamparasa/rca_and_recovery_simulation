from arth_rca.parser.xer_parser import XERParser
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from pathlib import Path

# 1. Check QTS-1281 in both files
p1 = XERParser().parse_file(Path('xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer'))
p2 = XERParser().parse_file(Path('xer_files/247011 08-18 (1).xer'))

t1_1281 = [t for t in p1.tasks.values() if t.task_code == 'QTS-1281']
t2_1281 = [t for t in p2.tasks.values() if t.task_code == 'QTS-1281']

print("=================================================================")
print("QTS-1281 CROSS-DATABASE VERIFICATION:")
print("FILE 1 (Phoenix PHX3DC1 Baseline):")
for t in t1_1281:
    print(f"  Task ID:   {t.task_id}")
    print(f"  Task Code: {t.task_code}")
    print(f"  Task Name: '{t.task_name}'")
    print(f"  Task Type: {t.task_type}")
    print(f"  Status:    {t.status_code}")
    print(f"  Proj ID:   {t.proj_id}")
    print(f"  P6 Float:  {t.total_float_hr_cnt/8}d")

print("\nFILE 2 (Project 247011 Update):")
for t in t2_1281:
    print(f"  Task ID:   {t.task_id}")
    print(f"  Task Code: {t.task_code}")
    print(f"  Task Name: '{t.task_name}'")
    print(f"  Task Type: {t.task_type}")
    print(f"  Status:    {t.status_code}")
    print(f"  Proj ID:   {t.proj_id}")
    print(f"  P6 Float:  {t.total_float_hr_cnt/8}d")
print("=================================================================")

# 2. Recompute exact reduction ratios for discrete delayed population
for name, p in [('File 2 (247011)', p2), ('File 1 (PHX3DC1)', p1)]:
    proj = next(iter(p.projects.values()))
    proj_data_dates = {pid: pr.last_recalc_date for pid, pr in p.projects.items()}
    proj_late_anchors = {pid: pr.must_finish_by_date for pid, pr in p.projects.items() if pr.must_finish_by_date}

    cals = {}
    for cid, c in p.calendars.items():
        wd, hol, wex = parse_p6_clndr_data(c.clndr_data or '')
        cals[cid] = CPMCalendarInput(clndr_id=cid, name=c.clndr_name, working_days=wd, work_hours_per_day=c.day_hr_cnt, holidays=hol, work_exceptions=wex)

    acts = {
        tid: CPMActivityInput(
            task_id=t.task_id, task_code=t.task_code, calendar_id=t.clndr_id or 1, proj_id=t.proj_id,
            original_duration_days=t.target_durn_hr_cnt / 8.0, remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
            status='COMPLETED' if t.status_code == 'TK_Complete' else ('IN_PROGRESS' if t.status_code == 'TK_Active' else 'NOT_STARTED'),
            act_start_date=t.act_start_date, act_finish_date=t.act_end_date,
            cstr_type=t.cstr_type, cstr_date=t.cstr_date, is_milestone='Mile' in t.task_type,
        )
        for tid, t in p.tasks.items()
    }

    rels = [
        CPMRelationshipInput(
            rel_id=pr.task_pred_id, pred_task_id=pr.pred_task_id, succ_task_id=pr.task_id,
            rel_type='FS' if pr.pred_type == 'PR_FS' else ('SS' if pr.pred_type == 'PR_SS' else ('FF' if pr.pred_type == 'PR_FF' else 'SF')),
            lag_days=pr.lag_hr_cnt / 8.0,
        )
        for pr in p.predecessors
    ]

    options = CPMOptions(data_date=proj.last_recalc_date, must_finish_by_date=proj.must_finish_by_date)
    cpm_res = run_cpm(acts, rels, cals, options, project_data_dates=proj_data_dates, project_late_anchors=proj_late_anchors)
    
    # Filter discrete tasks only (excluding LOE/WBS)
    discrete_delayed = [
        tid for tid, act in cpm_res.activities.items() 
        if acts[tid].status != 'COMPLETED' and act.total_float_days < -0.01 and p.tasks[tid].task_type not in ('TT_LOE', 'TT_WBS')
    ]
    
    # Run driver detection on discrete
    res = detect_negative_float_drivers(cpm_res, acts, rels)
    # Exclude any LOE driver heads if any
    discrete_driver_heads = [d for d in res.drivers if p.tasks[d.driver_task_id].task_type not in ('TT_LOE', 'TT_WBS')]
    
    disc_count = len(discrete_delayed)
    head_count = len(discrete_driver_heads)
    ratio = (1.0 - head_count / disc_count) * 100.0 if disc_count > 0 else 0.0
    
    print(f"\n{name} DISCRETE METRICS:")
    print(f"  Discrete Delayed Activities: {disc_count}")
    print(f"  Discrete Root Driver Heads:  {head_count}")
    print(f"  Convergence Nodes:           {len(res.convergence_nodes)}")
    print(f"  Exact Reduction Ratio:       {ratio:.1f}% ({head_count} drivers explain {disc_count} delayed tasks)")
