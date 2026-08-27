"""
Unit tests for pure-function CPM engine.
"""

from datetime import datetime, date
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


def test_simple_cpm_forward_backward():
    # Calendar: 5-Day
    cal = CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4})
    cals = {1: cal}

    # Activities: A (2 days) -> B (3 days)
    acts = {
        1: CPMActivityInput(task_id=1, task_code="A", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
        2: CPMActivityInput(task_id=2, task_code="B", calendar_id=1, original_duration_days=3.0, remaining_duration_days=3.0),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0)
    ]
    options = CPMOptions(data_date=datetime(2026, 9, 1, 8, 0))

    res = run_cpm(acts, rels, cals, options)

    assert res.activities[1].early_start.date() == date(2026, 9, 1)
    assert res.activities[1].early_finish.date() == date(2026, 9, 2)
    assert res.activities[2].early_start.date() == date(2026, 9, 3)
    assert res.activities[2].early_finish.date() == date(2026, 9, 7)  # skips Sat/Sun (Sep 5, 6)

    assert res.activities[1].total_float_days == 0.0
    assert res.activities[2].total_float_days == 0.0
    assert res.relationships[1].is_driving is True


def test_driving_ties_both_flagged():
    # Predecessors A (2 days) and B (2 days) both feed C (1 day)
    cal = CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4})
    cals = {1: cal}

    acts = {
        1: CPMActivityInput(task_id=1, task_code="A", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
        2: CPMActivityInput(task_id=2, task_code="B", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0),
        3: CPMActivityInput(task_id=3, task_code="C", calendar_id=1, original_duration_days=1.0, remaining_duration_days=1.0),
    }
    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
    ]
    options = CPMOptions(data_date=datetime(2026, 9, 1, 8, 0))

    res = run_cpm(acts, rels, cals, options)

    # Both A->C and B->C must be flagged is_driving=True (Ties preserved)
    assert res.relationships[1].is_driving is True
    assert res.relationships[2].is_driving is True
