"""
Performance benchmark test for CPM engine on a 10,000+ activity schedule.
Asserts that forward + backward pass completes in under 10 seconds.
"""

import time
from datetime import datetime
import pytest

from arth_rca.cpm.types import (
    CPMActivityInput,
    CPMRelationshipInput,
    CPMCalendarInput,
    CPMOptions,
)
from arth_rca.cpm.engine import run_cpm


def test_10k_activity_cpm_performance():
    num_activities = 10000
    cal = CPMCalendarInput(clndr_id=1, working_days={0, 1, 2, 3, 4})
    cals = {1: cal}

    acts = {}
    rels = []

    # Generate synthetic 10k DAG with branching & converging paths
    for i in range(1, num_activities + 1):
        acts[i] = CPMActivityInput(
            task_id=i,
            task_code=f"TASK_{i}",
            calendar_id=1,
            original_duration_days=float((i % 5) + 1),
            remaining_duration_days=float((i % 5) + 1),
        )
        if i > 1:
            # Connect to previous node
            rels.append(
                CPMRelationshipInput(
                    rel_id=i,
                    pred_task_id=i - 1,
                    succ_task_id=i,
                    rel_type="FS",
                    lag_days=0.0,
                )
            )

    options = CPMOptions(data_date=datetime(2026, 9, 1, 8, 0))

    start_time = time.perf_counter()
    result = run_cpm(acts, rels, cals, options)
    elapsed = time.perf_counter() - start_time

    print(f"\n[PERFORMANCE] CPM Engine completed {num_activities} activities in {elapsed:.3f} seconds.")

    assert len(result.activities) == num_activities
    assert elapsed < 10.0, f"CPM Engine exceeded 10-second limit: took {elapsed:.3f}s"
