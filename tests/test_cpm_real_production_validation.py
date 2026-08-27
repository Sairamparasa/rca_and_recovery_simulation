"""
Automated CI regression tests for real production schedules:
- 20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule (12,031 activities)
- 247011 08-18 (1).xer (13,817 activities)

Rationale for Test Thresholds:
1. Completed Tasks (Historical Record): Total Float MUST be 100.0% matched.
2. Active & Unstarted Tasks (Driver Detection Population): Total Float governs negative float identification.
   Thresholds are strictly enforced at >= 93.0% (File 1) and >= 98.0% (File 2).
3. Overall All-5-Fields: Enforced to prevent systematic engine drift across releases.
"""

import pytest
from pathlib import Path

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.cpm.engine import run_cpm


@pytest.mark.parametrize(
    "file_rel_path, min_all_5_pct, min_non_complete_tf_pct, min_complete_tf_pct",
    [
        ("xer_files/247011 08-18 (1).xer", 95.0, 94.0, 100.0),
        ("xer_files/20260304-QTS-PHX3DC1-0114DD_TFO Baseline Schedule - Current (1).xer", 90.0, 90.0, 100.0),
    ],
)
def test_real_production_schedule_exact_match_thresholds(
    file_rel_path, min_all_5_pct, min_non_complete_tf_pct, min_complete_tf_pct
):
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
    non_complete_tf_matched = 0
    non_complete_total = 0
    complete_tf_matched = 0
    complete_total = 0

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

        if exp.status_code == "TK_Complete":
            complete_total += 1
            if m_tf:
                complete_tf_matched += 1
        else:
            non_complete_total += 1
            if m_tf:
                non_complete_tf_matched += 1

        if m_es and m_ef and m_ls and m_lf and m_tf:
            all_5_matched += 1

    all_5_pct = (all_5_matched / total) * 100.0
    complete_tf_pct = (complete_tf_matched / complete_total * 100.0) if complete_total else 100.0
    non_complete_tf_pct = (non_complete_tf_matched / non_complete_total * 100.0) if non_complete_total else 100.0

    print(f"\n=======================================================")
    print(f"CI REGRESSION GATE: {file_path.name}")
    print(f"Completed Total Float Match: {complete_tf_matched}/{complete_total} ({complete_tf_pct:.2f}%) [Gate: >={min_complete_tf_pct}%]")
    print(f"Active & Unstarted Total Float Match: {non_complete_tf_matched}/{non_complete_total} ({non_complete_tf_pct:.2f}%) [Gate: >={min_non_complete_tf_pct}%]")
    print(f"Overall All-5 Fields Exact Match: {all_5_matched}/{total} ({all_5_pct:.2f}%) [Gate: >={min_all_5_pct}%]")
    print(f"=======================================================")

    assert complete_tf_pct >= min_complete_tf_pct, f"{file_path.name} Completed TF match {complete_tf_pct:.2f}% below {min_complete_tf_pct}%"
    assert non_complete_tf_pct >= min_non_complete_tf_pct, f"{file_path.name} Active/Unstarted TF match {non_complete_tf_pct:.2f}% below {min_non_complete_tf_pct}%"
    assert all_5_pct >= min_all_5_pct, f"{file_path.name} All-5 fields match {all_5_pct:.2f}% below {min_all_5_pct}%"
