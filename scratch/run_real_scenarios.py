from arth_rca.parser.xer_parser import XERParser
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.classification import classify_relationship
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.simulation.engine import run_simulation
from arth_rca.simulation.levers import CrashLever, FastTrackLever, CalendarChangeLever
from arth_rca.db.models import generate_relationship_key, RelationshipClassification
from pathlib import Path

# Load File 1: Phoenix Baseline PHX3DC1
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

options1 = CPMOptions(data_date=proj1.last_recalc_date, must_finish_by_date=proj1.must_finish_by_date)
cpm_res1 = run_cpm(acts1, rels1, cals1, options1, project_data_dates=proj_data_dates1, project_late_anchors=proj_late_anchors1)

# Generate classifications for File 1 FS relationships
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

# SCENARIO 1 (File 1): Target Driver Head QTS-41811 (Duration 5d -> 1d)
s1_lever = CrashLever(task_code="QTS-41811", reduction_days=4.0, description="Crash driver QTS-41811 from 5d to 1d")
sim1, diff1 = run_simulation(acts1, rels1, cals1, options1, [s1_lever], class_map1, project_data_dates=proj_data_dates1, project_late_anchors=proj_late_anchors1, scenario_name="Scenario 1: Crash Top Driver QTS-41811")

# SCENARIO 2 (File 1): Fast-Track Real SOFT_RESOURCE relationship QTS-41811 -> QTS-41831 (FS -> SS with 1d lag)
k_soft = generate_relationship_key("QTS-41811", "QTS-41831", "FS")
class_map1[k_soft] = RelationshipClassification(relationship_key=k_soft, project_id=proj1.proj_id, constraint_type="SOFT_RESOURCE", confidence=0.85, classification_source="PM_REVIEWED")
s2_lever = FastTrackLever(pred_task_code="QTS-41811", succ_task_code="QTS-41831", new_relationship_type="SS", new_lag_days=1.0, description="Fast-track trade handoff sequence to Start-to-Start with 1-day lead")
sim2, diff2 = run_simulation(acts1, rels1, cals1, options1, [s2_lever], class_map1, project_data_dates=proj_data_dates1, project_late_anchors=proj_late_anchors1, scenario_name="Scenario 2: Fast-Track SOFT_RESOURCE Pair QTS-41811 -> QTS-41831")

# Load File 2: Project 247011 Update
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

options2 = CPMOptions(data_date=proj2.last_recalc_date, must_finish_by_date=proj2.must_finish_by_date)
# SCENARIO 3 (File 2): Crash Critical Delayed Driver Chain on QTS-28981 (Duration 40d -> 15d)
s3_lever = CrashLever(task_code="QTS-28981", reduction_days=25.0, description="Crash driver QTS-28981 from 40d to 15d")
sim3, diff3 = run_simulation(acts2, rels2, cals2, options2, [s3_lever], {}, project_data_dates=proj_data_dates2, project_late_anchors=proj_late_anchors2, scenario_name="Scenario 3: Crash Top Driver QTS-28981 in File 2")

for sc_num, (sc_name, diff, sim_cpm, base_cpm, p_obj, acts_map) in enumerate([
    ('Scenario 1 (File 1: Crash Driver QTS-41811)', diff1, sim1, cpm_res1, p1, acts1),
    ('Scenario 2 (File 1: Fast-Track QTS-41811 -> QTS-41831)', diff2, sim2, cpm_res1, p1, acts1),
    ('Scenario 3 (File 2: Crash Driver QTS-28981)', diff3, sim3, None, p2, acts2),
], 1):
    print(f"\n=======================================================")
    print(f"{sc_name.upper()}")
    print(f"=======================================================")
    print(f"Baseline Project Finish Date:      {diff.baseline_finish_date}")
    print(f"Simulated Project Finish Date:     {diff.simulated_finish_date}")
    print(f"Working Days Recovered:            {diff.days_recovered} days")
    print(f"Baseline Discrete Delayed Count:   {diff.baseline_discrete_delayed_count}")
    print(f"Simulated Discrete Delayed Count:  {diff.simulated_discrete_delayed_count} (Recovered {diff.discrete_delayed_recovered_count} delayed tasks)")
    print(f"Critical Path Shifted:             {diff.critical_path_shifted}")
    print(f"Top 5 Affected Activity Float Deltas:")
    for ad in diff.activity_deltas[:5]:
        print(f"  - {ad.task_code}: Baseline TF={ad.baseline_total_float_days}d -> Simulated TF={ad.simulated_total_float_days}d (Float Delta = +{ad.float_delta_days}d, EF {ad.baseline_early_finish} -> {ad.simulated_early_finish})")
