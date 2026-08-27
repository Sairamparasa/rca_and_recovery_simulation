"""
Real XER Driver Reduction Test per Section 4 of Complete_Implementation_Plan.md.
Tests driver identification and reduction ratio against BOTH real production schedules:
1. 20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule (12,031 activities)
2. 247011 08-18 (1).xer (13,817 activities)
"""

import pytest
from pathlib import Path
import time

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.cpm.engine import run_cpm
from arth_rca.analytics.driver_detection import detect_negative_float_drivers


@pytest.mark.parametrize(
    "file_rel_path, min_reduction_ratio_pct",
    [
        ("xer_files/247011 08-18 (1).xer", 60.0),
        ("xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer", 60.0),
    ],
)
def test_real_schedule_driver_reduction_ratio(file_rel_path, min_reduction_ratio_pct):
    f_path = Path(file_rel_path)
    if not f_path.exists():
        pytest.skip(f"Real XER file not found: {f_path}")

    # 1. Parse Real Schedule
    t0 = time.perf_counter()
    parser = XERParser()
    parsed = parser.parse_file(f_path)
    proj = next(iter(parsed.projects.values()))
    proj_data_dates = {pid: p.last_recalc_date for pid, p in parsed.projects.items()}
    proj_late_anchors = {pid: p.must_finish_by_date for pid, p in parsed.projects.items() if p.must_finish_by_date}

    cals = {}
    for cid, c in parsed.calendars.items():
        wd, hol, wex = parse_p6_clndr_data(c.clndr_data or "")
        cals[cid] = CPMCalendarInput(
            clndr_id=cid,
            name=c.clndr_name,
            working_days=wd,
            work_hours_per_day=c.day_hr_cnt,
            holidays=hol,
            work_exceptions=wex,
        )

    acts = {
        tid: CPMActivityInput(
            task_id=t.task_id,
            task_code=t.task_code,
            calendar_id=t.clndr_id or 1,
            proj_id=t.proj_id,
            original_duration_days=t.target_durn_hr_cnt / 8.0,
            remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
            status="COMPLETED" if t.status_code == "TK_Complete" else ("IN_PROGRESS" if t.status_code == "TK_Active" else "NOT_STARTED"),
            act_start_date=t.act_start_date,
            act_finish_date=t.act_end_date,
            cstr_type=t.cstr_type,
            cstr_date=t.cstr_date,
            is_milestone="Mile" in t.task_type,
        )
        for tid, t in parsed.tasks.items()
    }

    rels = [
        CPMRelationshipInput(
            rel_id=p.task_pred_id,
            pred_task_id=p.pred_task_id,
            succ_task_id=p.task_id,
            rel_type="FS" if p.pred_type == "PR_FS" else ("SS" if p.pred_type == "PR_SS" else ("FF" if p.pred_type == "PR_FF" else "SF")),
            lag_days=p.lag_hr_cnt / 8.0,
        )
        for p in parsed.predecessors
    ]

    options = CPMOptions(
        data_date=proj.last_recalc_date,
        must_finish_by_date=proj.must_finish_by_date,
    )

    # 2. Run CPM Engine
    cpm_result = run_cpm(acts, rels, cals, options, project_data_dates=proj_data_dates, project_late_anchors=proj_late_anchors)

    # 3. Detect Drivers & Blast Radius Trees
    driver_res = detect_negative_float_drivers(cpm_result, parsed.tasks, rels, snapshot_id=1)
    t_elapsed = time.perf_counter() - t0

    # 4. Assertions & Reduction Ratio Calculations
    total_activities = len(parsed.tasks)
    total_neg_float = driver_res.total_negative_float_activities
    driver_heads_count = driver_res.driver_head_count

    print(f"\n=======================================================")
    print(f"DRIVER REDUCTION ANALYSIS: {f_path.name}")
    print(f"Total Activities in Schedule: {total_activities}")
    print(f"Total Negative Float Activities: {total_neg_float}")
    print(f"Driver Heads Identified: {driver_heads_count}")
    print(f"Convergence Nodes: {len(driver_res.convergence_nodes)}")
    print(f"Analysis Execution Time: {t_elapsed:.2f} seconds")

    if total_neg_float > 0:
        reduction_ratio = (1.0 - (driver_heads_count / total_neg_float)) * 100.0
        print(f"Driver Reduction Ratio: {reduction_ratio:.1f}% reduction ({driver_heads_count} root drivers explain {total_neg_float} delayed activities)")
        print(f"=======================================================")
        assert driver_heads_count <= total_neg_float
        assert driver_heads_count > 0
        assert reduction_ratio >= min_reduction_ratio_pct
    else:
        print(f"Schedule has 0 negative float activities (on-time schedule).")
        print(f"=======================================================")
        assert driver_heads_count == 0
