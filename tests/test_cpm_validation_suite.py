"""
CRITICAL VALIDATION TEST SUITE:
Verifies CPM engine output against Primavera P6 schedules with rich per-activity discrepancy diagnostics.
"""

from pathlib import Path
from datetime import datetime, date
import pytest

from arth_rca.parser.xer_parser import XERParser
from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
    FloatCalcMode,
    OOSMode,
    CriticalPathType,
)
from arth_rca.cpm.calendar import parse_p6_clndr_data
from arth_rca.cpm.engine import run_cpm

FIXTURES_DIR = Path(__file__).parent / "fixtures"
XER_FILES_DIR = Path(__file__).parent.parent / "xer_files"

FIXTURE_FILES = [
    FIXTURES_DIR / "fixture_standard_cpm.xer",
    FIXTURES_DIR / "fixture_multi_calendar_holidays.xer",
    FIXTURES_DIR / "fixture_constraints_oos.xer",
]


@pytest.mark.parametrize("fixture_path", FIXTURE_FILES)
def test_cpm_exact_match_against_p6_baseline(fixture_path):
    parser = XERParser()
    parsed = parser.parse_file(fixture_path)
    proj = next(iter(parsed.projects.values()))
    
    # 1. Parse Project Calculation Options
    f_calc_mode_map = {
        "START_DATES": FloatCalcMode.START_DATES,
        "FINISH_DATES": FloatCalcMode.FINISH_DATES,
        "MIN_START_FINISH": FloatCalcMode.MIN_START_FINISH,
    }
    f_calc_mode = f_calc_mode_map.get(proj.f_calc_mode, FloatCalcMode.START_DATES)

    oos_mode_map = {
        "RETAINED_LOGIC": OOSMode.RETAINED_LOGIC,
        "PROGRESS_OVERRIDE": OOSMode.PROGRESS_OVERRIDE,
        "ACTUAL_DATES": OOSMode.ACTUAL_DATES,
    }
    oos_mode = oos_mode_map.get(proj.oos_mode, OOSMode.RETAINED_LOGIC)

    critical_path_type = (
        CriticalPathType.LONGEST_PATH
        if proj.critical_path_type == "LONGEST_PATH"
        else CriticalPathType.TOTAL_FLOAT
    )

    data_date = proj.last_recalc_date or proj.plan_start_date or datetime(2026, 9, 1, 8, 0)
    options = CPMOptions(
        data_date=data_date,
        f_calc_mode=f_calc_mode,
        oos_mode=oos_mode,
        critical_path_type=critical_path_type,
        must_finish_by_date=proj.must_finish_by_date,
    )

    # 2. Build Calendars using P6 clndr_data parser
    cals = {}
    for clndr_id, c in parsed.calendars.items():
        if c.clndr_data:
            wd, hol = parse_p6_clndr_data(c.clndr_data)
        else:
            wd = {0, 1, 2, 3, 4, 5, 6} if "7" in c.clndr_name else {0, 1, 2, 3, 4}
            hol = set()

        cals[clndr_id] = CPMCalendarInput(
            clndr_id=clndr_id,
            name=c.clndr_name,
            working_days=wd,
            work_hours_per_day=c.day_hr_cnt,
            holidays=hol,
        )

    # 3. Build Raw CPM Activities
    acts = {}
    for t_id, t in parsed.tasks.items():
        status = "NOT_STARTED"
        if t.status_code == "TK_Active":
            status = "IN_PROGRESS"
        elif t.status_code == "TK_Complete":
            status = "COMPLETED"

        acts[t_id] = CPMActivityInput(
            task_id=t.task_id,
            task_code=t.task_code,
            calendar_id=t.clndr_id or 1,
            original_duration_days=t.target_durn_hr_cnt / 8.0,
            remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
            status=status,
            act_start_date=t.act_start_date,
            act_finish_date=t.act_end_date,
            cstr_type=t.cstr_type,
            cstr_date=t.cstr_date,
            is_milestone="Mile" in t.task_type,
        )

    # 4. Build Relationships
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

    # 5. Execute Pure CPM Engine
    cpm_result = run_cpm(acts, rels, cals, options)

    # 6. Detailed Diagnostics & Exact Match Check
    total_activities = len(parsed.tasks)
    matched_activities = 0
    discrepancies = []

    for t_id, expected_task in parsed.tasks.items():
        computed = cpm_result.activities[t_id]
        
        exp_es = expected_task.early_start_date.date() if expected_task.early_start_date else None
        exp_ef = expected_task.early_end_date.date() if expected_task.early_end_date else None
        exp_ls = expected_task.late_start_date.date() if expected_task.late_start_date else None
        exp_lf = expected_task.late_end_date.date() if expected_task.late_end_date else None
        exp_tf_days = expected_task.total_float_hr_cnt / 8.0

        comp_es = computed.early_start.date()
        comp_ef = computed.early_finish.date()
        comp_ls = computed.late_start.date()
        comp_lf = computed.late_finish.date()
        comp_tf_days = computed.total_float_days

        field_diffs = {}
        if comp_es != exp_es:
            field_diffs["ES"] = {"expected": exp_es, "computed": comp_es}
        if comp_ef != exp_ef:
            field_diffs["EF"] = {"expected": exp_ef, "computed": comp_ef}
        if comp_ls != exp_ls:
            field_diffs["LS"] = {"expected": exp_ls, "computed": comp_ls}
        if comp_lf != exp_lf:
            field_diffs["LF"] = {"expected": exp_lf, "computed": comp_lf}
        if comp_tf_days != exp_tf_days:
            field_diffs["TF"] = {"expected": exp_tf_days, "computed": comp_tf_days, "delta_days": comp_tf_days - exp_tf_days}

        if not field_diffs:
            matched_activities += 1
        else:
            discrepancies.append({
                "task_code": expected_task.task_code,
                "task_name": expected_task.task_name,
                "status": expected_task.status_code,
                "diffs": field_diffs,
            })

    match_rate = (matched_activities / total_activities) * 100.0
    print(f"\n=======================================================")
    print(f"CPM VALIDATION REPORT: {fixture_path.name}")
    print(f"Total Activities: {total_activities} | Matched: {matched_activities} | Match Rate: {match_rate:.2f}%")
    print(f"=======================================================")

    if discrepancies:
        print(f"Discrepancies found in {len(discrepancies)} activities:")
        for disc in discrepancies[:10]:
            print(f"  [MISMATCH] Task {disc['task_code']} ({disc['status']}):")
            for field_name, diff_info in disc["diffs"].items():
                print(f"    - {field_name}: Computed={diff_info.get('computed')} vs Expected={diff_info.get('expected')}")
        if len(discrepancies) > 10:
            print(f"  ... and {len(discrepancies) - 10} more mismatched activities.")

    assert match_rate == 100.0, (
        f"CPM Validation failed on {fixture_path.name}. Match rate: {match_rate:.2f}% (Expected 100.0%). "
        f"{len(discrepancies)} discrepancies reported above."
    )
