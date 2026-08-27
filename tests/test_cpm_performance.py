"""
Performance benchmark tests for CPM engine:
1. 10,000+ activity schedule with realistic branching & converging network density.
2. Real-world 12,000+ activity production schedule from xer_files.
"""

import time
import random
from pathlib import Path
from datetime import datetime
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

XER_FILES_DIR = Path(__file__).parent.parent / "xer_files"


def test_10k_realistic_branching_cpm_performance():
    """Benchmark CPM engine on a 10,000-activity DAG with realistic branching (in/out degree 2-4)."""
    num_activities = 10000
    cal = CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4})
    cals = {1: cal}

    acts = {}
    rels = []
    rel_id = 1

    # Generate multi-branch DAG with convergence
    for i in range(1, num_activities + 1):
        acts[i] = CPMActivityInput(
            task_id=i,
            task_code=f"TASK_{i:05d}",
            calendar_id=1,
            original_duration_days=float((i % 10) + 1),
            remaining_duration_days=float((i % 10) + 1),
        )

        if i > 1:
            # Primary predecessor
            pred_1 = max(1, i - 1)
            rels.append(
                CPMRelationshipInput(
                    rel_id=rel_id,
                    pred_task_id=pred_1,
                    succ_task_id=i,
                    rel_type="FS",
                    lag_days=0.0,
                )
            )
            rel_id += 1

            # Cross-branch predecessor for realistic network density
            if i > 5 and i % 3 == 0:
                pred_2 = max(1, i - (i % 7) - 1)
                if pred_2 < i:
                    rels.append(
                        CPMRelationshipInput(
                            rel_id=rel_id,
                            pred_task_id=pred_2,
                            succ_task_id=i,
                            rel_type="SS" if i % 2 == 0 else "FF",
                            lag_days=1.0,
                        )
                    )
                    rel_id += 1

    options = CPMOptions(data_date=datetime(2026, 9, 1, 8, 0))

    start_time = time.perf_counter()
    result = run_cpm(acts, rels, cals, options)
    elapsed = time.perf_counter() - start_time

    print(f"\n[BENCHMARK] Realistic Branching DAG: {num_activities} activities, {len(rels)} relationships in {elapsed:.3f}s")

    assert len(result.activities) == num_activities
    assert elapsed < 10.0, f"CPM Engine exceeded 10-second limit: took {elapsed:.3f}s"


def test_real_production_schedule_performance():
    """Benchmark CPM engine on real 12,031 activity P6 datacenter schedule."""
    real_files = list(XER_FILES_DIR.glob("*.xer"))
    if not real_files:
        pytest.skip("No real XER files found in xer_files directory")

    target_file = real_files[0]
    parser = XERParser()
    parsed = parser.parse_file(target_file)
    proj = next(iter(parsed.projects.values()))

    cals = {}
    for cid, c in parsed.calendars.items():
        wd, hol = parse_p6_clndr_data(c.clndr_data or "")
        cals[cid] = CPMCalendarInput(
            clndr_id=cid,
            name=c.clndr_name,
            working_days=wd,
            work_hours_per_day=c.day_hr_cnt,
            holidays=hol,
        )

    acts = {}
    for tid, t in parsed.tasks.items():
        status = "NOT_STARTED"
        if t.status_code == "TK_Active":
            status = "IN_PROGRESS"
        elif t.status_code == "TK_Complete":
            status = "COMPLETED"

        acts[tid] = CPMActivityInput(
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
        data_date=proj.last_recalc_date or proj.plan_start_date or datetime(2026, 1, 14, 8, 0),
        f_calc_mode=FloatCalcMode.START_DATES,
        oos_mode=OOSMode.RETAINED_LOGIC,
        critical_path_type=CriticalPathType.TOTAL_FLOAT,
        must_finish_by_date=proj.must_finish_by_date,
    )

    start_time = time.perf_counter()
    result = run_cpm(acts, rels, cals, options)
    elapsed = time.perf_counter() - start_time

    print(f"\n[BENCHMARK] Real Production Schedule '{target_file.name}': {len(acts)} activities, {len(rels)} relationships in {elapsed:.3f}s")

    assert len(result.activities) == len(acts)
    assert elapsed < 10.0, f"Real schedule CPM exceeded 10-second limit: took {elapsed:.3f}s"
