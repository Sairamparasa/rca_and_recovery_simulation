"""
Unit and integration tests for Phase 1 analytics:
- Driver Detection & Blast Radius Trees
- Convergence Node Identification
- Deterministic Root-Cause Typing
- Configurable Impact Scoring
- DCMA 14-Point Health Checks
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

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
from arth_rca.analytics.driver_detection import detect_negative_float_drivers, DriverAnalysisResult
from arth_rca.analytics.root_cause import classify_driver_root_cause, RootCauseResult
from arth_rca.analytics.impact_scoring import calculate_driver_impact_score, ScoringConfig
from arth_rca.analytics.dcma import run_dcma_14_point_assessment, DCMAAssessmentReport


def test_driver_detection_and_blast_radius():
    # Construct a small network with 2 drivers converging on a milestone
    # Driver 1: A1 -> A2 -> C (convergence)
    # Driver 2: B1 -> C (convergence)
    cals = {1: CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4})}
    options = CPMOptions(data_date=datetime(2026, 9, 1, 8, 0), must_finish_by_date=datetime(2026, 9, 5, 17, 0))

    acts = {
        1: CPMActivityInput(task_id=1, task_code="A1", calendar_id=1, original_duration_days=3.0, remaining_duration_days=3.0, status="NOT_STARTED"),
        2: CPMActivityInput(task_id=2, task_code="A2", calendar_id=1, original_duration_days=3.0, remaining_duration_days=3.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="B1", calendar_id=1, original_duration_days=6.0, remaining_duration_days=6.0, status="NOT_STARTED"),
        4: CPMActivityInput(task_id=4, task_code="C_MILE", calendar_id=1, original_duration_days=2.0, remaining_duration_days=2.0, status="NOT_STARTED", is_milestone=True),
    }

    rels = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=4, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=3, pred_task_id=3, succ_task_id=4, rel_type="FS", lag_days=0.0),
    ]

    cpm_res = run_cpm(acts, rels, cals, options)

    # Class-like mock for raw tasks
    class MockTask:
        def __init__(self, tid, code, status, is_mile=False):
            self.task_id = tid
            self.task_code = code
            self.status_code = status
            self.task_type = "TT_FinMile" if is_mile else "TT_Task"

    raw_tasks = {
        1: MockTask(1, "A1", "TK_NotStart"),
        2: MockTask(2, "A2", "TK_NotStart"),
        3: MockTask(3, "B1", "TK_NotStart"),
        4: MockTask(4, "C_MILE", "TK_NotStart", is_mile=True),
    }

    res = detect_negative_float_drivers(cpm_res, raw_tasks, rels, snapshot_id=101)

    assert res.total_negative_float_activities == 4
    assert res.driver_head_count == 2
    driver_codes = {d.driver_task_code for d in res.drivers}
    assert driver_codes == {"A1", "B1"}
    assert "C_MILE" in res.convergence_nodes


def test_root_cause_typing():
    class MockTask:
        def __init__(self, tid, code, status, cstr_type=None, cstr_date=None, target_durn=8.0):
            self.task_id = tid
            self.task_code = code
            self.status_code = status
            self.cstr_type = cstr_type
            self.cstr_date = cstr_date
            self.target_durn_hr_cnt = target_durn

    cpm_act = run_cpm(
        {1: CPMActivityInput(task_id=1, task_code="T1", calendar_id=1, original_duration_days=1.0, remaining_duration_days=1.0)},
        [],
        {1: CPMCalendarInput(clndr_id=1)},
        CPMOptions(data_date=datetime(2026, 9, 1, 8, 0)),
    ).activities[1]

    # Test Hard Constraint
    t_cstr = MockTask(1, "T1", "TK_NotStart", cstr_type="CS_MANDFIN", cstr_date=datetime(2026, 9, 10))
    rc_cstr = classify_driver_root_cause(1, t_cstr, cpm_act, [], {1: t_cstr})
    assert rc_cstr.category == "constraint"
    assert rc_cstr.confidence_score == 1.0

    # Test Out of Sequence
    t_oos = MockTask(2, "T2", "TK_Active")
    t_pred = MockTask(3, "T_PRED", "TK_NotStart")
    class MockPred:
        def __init__(self, pid, sid):
            self.pred_task_id = pid
            self.succ_task_id = sid
    rc_oos = classify_driver_root_cause(2, t_oos, cpm_act, [MockPred(3, 2)], {2: t_oos, 3: t_pred})
    assert rc_oos.category == "out_of_sequence"

    # Test External Delay (Duration Expansion)
    t_curr = MockTask(4, "T4", "TK_NotStart", target_durn=80.0)
    t_base = MockTask(4, "T4", "TK_NotStart", target_durn=40.0)
    rc_ext = classify_driver_root_cause(4, t_curr, cpm_act, [], {4: t_curr}, baseline_task=t_base)
    assert rc_ext.category == "external_delay"


def test_impact_scoring_configuration():
    score_default = calculate_driver_impact_score(
        downstream_activity_count=10,
        total_float_days=-20.0,
        milestone_count=2,
    )
    assert score_default > 0

    custom_cfg = ScoringConfig(
        float_magnitude_weight=2.0,
        milestone_weight=5.0,
        downstream_count_weight=1.5,
    )
    score_custom = calculate_driver_impact_score(
        downstream_activity_count=10,
        total_float_days=-20.0,
        milestone_count=2,
        config=custom_cfg,
    )
    assert score_custom > score_default


def test_dcma_14_point_assessment():
    f2 = Path("xer_files/247011 08-18 (1).xer")
    parser = XERParser()
    parsed = parser.parse_file(f2)
    proj = parsed.projects[236646]

    cals = {}
    for cid, c in parsed.calendars.items():
        wd, hol, wex = parse_p6_clndr_data(c.clndr_data or "")
        cals[cid] = CPMCalendarInput(clndr_id=cid, name=c.clndr_name, working_days=wd, work_hours_per_day=c.day_hr_cnt, holidays=hol, work_exceptions=wex)

    acts = {
        tid: CPMActivityInput(
            task_id=t.task_id, task_code=t.task_code, calendar_id=t.clndr_id or 1, proj_id=t.proj_id,
            original_duration_days=t.target_durn_hr_cnt / 8.0, remaining_duration_days=t.remain_durn_hr_cnt / 8.0,
            status="COMPLETED" if t.status_code == "TK_Complete" else ("IN_PROGRESS" if t.status_code == "TK_Active" else "NOT_STARTED"),
            act_start_date=t.act_start_date, act_finish_date=t.act_end_date,
            cstr_type=t.cstr_type, cstr_date=t.cstr_date, is_milestone="Mile" in t.task_type,
        )
        for tid, t in parsed.tasks.items()
    }

    rels = [
        CPMRelationshipInput(
            rel_id=p.task_pred_id, pred_task_id=p.pred_task_id, succ_task_id=p.task_id,
            rel_type="FS" if p.pred_type == "PR_FS" else ("SS" if p.pred_type == "PR_SS" else ("FF" if p.pred_type == "PR_FF" else "SF")),
            lag_days=p.lag_hr_cnt / 8.0,
        )
        for p in parsed.predecessors
    ]

    options = CPMOptions(data_date=proj.last_recalc_date, must_finish_by_date=proj.must_finish_by_date)
    cpm_result = run_cpm(acts, rels, cals, options)

    dcma_report = run_dcma_14_point_assessment(
        cpm_result=cpm_result,
        raw_tasks=parsed.tasks,
        raw_relationships=parsed.predecessors,
        data_date=proj.last_recalc_date,
        snapshot_id=1,
    )

    assert len(dcma_report.metrics) == 14
    assert dcma_report.overall_health_score > 0
    assert any(m.name == "Critical Path Test" for m in dcma_report.metrics)
