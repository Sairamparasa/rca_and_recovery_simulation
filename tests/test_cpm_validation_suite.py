"""
CRITICAL VALIDATION TEST SUITE:
Verifies 100% exact match (to the day) between the deterministic CPM engine output
and the native P6-calculated values across 3 real/benchmark schedule fixtures.
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
from arth_rca.cpm.engine import run_cpm

FIXTURES_DIR = Path(__file__).parent / "fixtures"

FIXTURE_FILES = [
    "fixture_standard_cpm.xer",
    "fixture_multi_calendar_holidays.xer",
    "fixture_constraints_oos.xer",
]


@pytest.mark.parametrize("fixture_name", FIXTURE_FILES)
def test_cpm_exact_match_against_p6_baseline(fixture_name):
    fixture_path = FIXTURES_DIR / fixture_name
    parser = XERParser()
    parsed = parser.parse_file(fixture_path)

    # 1. Parse Project Calculation Options
    proj = next(iter(parsed.projects.values()))
    
    # Map project options
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

    data_date = proj.plan_start_date or datetime(2026, 9, 1, 8, 0)
    options = CPMOptions(
        data_date=data_date,
        f_calc_mode=f_calc_mode,
        oos_mode=oos_mode,
        critical_path_type=critical_path_type,
        must_finish_by_date=proj.must_finish_by_date,
    )

    # 2. Build Calendars
    cals = {}
    for clndr_id, c in parsed.calendars.items():
        # Check if 7-day or 5-day
        working_days = {0, 1, 2, 3, 4, 5, 6} if "7" in c.clndr_name else {0, 1, 2, 3, 4}
        cals[clndr_id] = CPMCalendarInput(
            clndr_id=clndr_id,
            name=c.clndr_name,
            working_days=working_days,
            work_hours_per_day=c.day_hr_cnt,
        )

    # 3. Build Raw CPM Activities (Excluding computed fields)
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

    # 6. Compare Against Native P6 Expected Values
    total_activities = len(parsed.tasks)
    matched_activities = 0
    discrepancies = []

    for t_id, expected_task in parsed.tasks.items():
        computed = cpm_result.activities[t_id]
        
        # Expected dates from P6
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

        is_match = (
            comp_es == exp_es
            and comp_ef == exp_ef
            and comp_ls == exp_ls
            and comp_lf == exp_lf
            and comp_tf_days == exp_tf_days
        )

        if is_match:
            matched_activities += 1
        else:
            discrepancies.append({
                "task_code": expected_task.task_code,
                "expected": {"ES": exp_es, "EF": exp_ef, "LS": exp_ls, "LF": exp_lf, "TF": exp_tf_days},
                "computed": {"ES": comp_es, "EF": comp_ef, "LS": comp_ls, "LF": comp_lf, "TF": comp_tf_days},
            })

    match_rate = (matched_activities / total_activities) * 100.0
    print(f"\n--- Validation Report for {fixture_name} ---")
    print(f"Total Activities: {total_activities} | Matched: {matched_activities} | Match Rate: {match_rate:.2f}%")

    if discrepancies:
        print(f"Discrepancies found in {len(discrepancies)} activities:")
        for disc in discrepancies:
            print(f"  Activity {disc['task_code']}:")
            print(f"    Expected: {disc['expected']}")
            print(f"    Computed: {disc['computed']}")

    # MANDATORY ASSERTION: 100% EXACT MATCH REQUIRED
    assert match_rate == 100.0, f"CPM Validation failed on {fixture_name}. Match rate: {match_rate:.2f}% (Expected 100.0%)"
