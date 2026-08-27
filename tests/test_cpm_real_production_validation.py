"""
Automated CI regression tests for real production schedules:
- 20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule (12,031 activities)
- 247011 08-18 (1).xer (13,817 activities)
Enforces minimum exact-match thresholds to guard against engine regressions.
"""

import pytest
from pathlib import Path

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.cpm.engine import run_cpm


@pytest.mark.parametrize(
    "file_rel_path, min_all_5_match_pct, min_tf_match_pct",
    [
        ("xer_files/247011 08-18 (1).xer", 95.0, 99.0),
        ("xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer", 90.0, 92.0),
    ],
)
def test_real_production_schedule_exact_match_thresholds(file_rel_path, min_all_5_match_pct, min_tf_match_pct):
    file_path = Path(file_rel_path)
    if not file_path.exists():
        pytest.skip(f"Real production file not found: {file_path}")

    parser = XERParser()
    parsed = parser.parse_file(file_path)
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

    cpm_result = run_cpm(acts, rels, cals, options, project_data_dates=proj_data_dates, project_late_anchors=proj_late_anchors)

    total = len(parsed.tasks)
    all_5_matched = 0
    tf_matched = 0

    for tid, exp in parsed.tasks.items():
        comp = cpm_result.activities[tid]
        exp_es = exp.early_start_date.date() if exp.early_start_date else None
        exp_ef = exp.early_end_date.date() if exp.early_end_date else None
        exp_ls = exp.late_start_date.date() if exp.late_start_date else None
        exp_lf = exp.late_end_date.date() if exp.late_end_date else None
        exp_tf = round(exp.total_float_hr_cnt / 8.0, 1)

        m_es = comp.early_start.date() == exp_es
        m_ef = comp.early_finish.date() == exp_ef
        m_ls = comp.late_start.date() == exp_ls
        m_lf = comp.late_finish.date() == exp_lf
        m_tf = round(comp.total_float_days, 1) == exp_tf

        if m_tf:
            tf_matched += 1
        if m_es and m_ef and m_ls and m_lf and m_tf:
            all_5_matched += 1

    all_5_pct = (all_5_matched / total) * 100.0
    tf_pct = (tf_matched / total) * 100.0

    print(f"\n{file_path.name}: All-5 Fields Match = {all_5_matched}/{total} ({all_5_pct:.2f}%) | TF Match = {tf_matched}/{total} ({tf_pct:.2f}%)")

    assert all_5_pct >= min_all_5_match_pct, f"{file_path.name} All-5 fields exact match {all_5_pct:.2f}% below threshold {min_all_5_match_pct}%"
    assert tf_pct >= min_tf_match_pct, f"{file_path.name} Total Float match {tf_pct:.2f}% below threshold {min_tf_match_pct}%"
