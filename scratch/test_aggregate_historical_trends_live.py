"""
Verification script: runs aggregate_historical_trends on real multi-snapshot data
and prints the resulting historical metrics (DCMA trends, milestone slippage, driver churn, float trends).
"""

from datetime import datetime
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.trend import aggregate_historical_trends, SnapshotDataPackage
from arth_rca.analytics.snapshot_diff import compute_snapshot_diff

def run_multi_snapshot_test():
    cal = {
        1: CPMCalendarInput(
            clndr_id=1,
            name="Standard 5-Day",
            working_days=[True, True, True, True, True, False, False],
            work_hours_per_day=8.0,
            holidays=[],
            work_exceptions={},
        )
    }

    # Snapshot 1: Baseline (2026-01-01)
    dd1 = datetime(2026, 1, 1, 8, 0)
    acts1 = {
        1: CPMActivityInput(task_id=1, task_code="QTS-28981", calendar_id=1, proj_id=1, original_duration_days=30.0, remaining_duration_days=30.0, status="NOT_STARTED"),
        2: CPMActivityInput(task_id=2, task_code="QTS-29661", calendar_id=1, proj_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="M_ENERGIZATION", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
        4: CPMActivityInput(task_id=4, task_code="M_COMMISSIONING", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
    }
    rels1 = [
        CPMRelationshipInput(rel_id=1, pred_task_id=1, succ_task_id=2, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=2, pred_task_id=2, succ_task_id=3, rel_type="FS", lag_days=0.0),
        CPMRelationshipInput(rel_id=3, pred_task_id=3, succ_task_id=4, rel_type="FS", lag_days=0.0),
    ]

    # Snapshot 2: 1-Month Update (2026-02-01) - QTS-28981 expanded duration by 10 days
    dd2 = datetime(2026, 2, 1, 8, 0)
    acts2 = {
        1: CPMActivityInput(task_id=1, task_code="QTS-28981", calendar_id=1, proj_id=1, original_duration_days=40.0, remaining_duration_days=40.0, status="IN_PROGRESS"),
        2: CPMActivityInput(task_id=2, task_code="QTS-29661", calendar_id=1, proj_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED"),
        3: CPMActivityInput(task_id=3, task_code="M_ENERGIZATION", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
        4: CPMActivityInput(task_id=4, task_code="M_COMMISSIONING", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
    }
    rels2 = list(rels1)

    # Snapshot 3: 2-Month Update (2026-03-01) - Hard constraint added on QTS-29661
    dd3 = datetime(2026, 3, 1, 8, 0)
    acts3 = {
        1: CPMActivityInput(task_id=1, task_code="QTS-28981", calendar_id=1, proj_id=1, original_duration_days=45.0, remaining_duration_days=45.0, status="IN_PROGRESS"),
        2: CPMActivityInput(task_id=2, task_code="QTS-29661", calendar_id=1, proj_id=1, original_duration_days=20.0, remaining_duration_days=20.0, status="NOT_STARTED", cstr_type="CS_MANDFIN", cstr_date=datetime(2026, 5, 1, 17, 0)),
        3: CPMActivityInput(task_id=3, task_code="M_ENERGIZATION", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
        4: CPMActivityInput(task_id=4, task_code="M_COMMISSIONING", calendar_id=1, proj_id=1, original_duration_days=0.0, remaining_duration_days=0.0, status="NOT_STARTED", is_milestone=True, task_type="TT_FinMile"),
    }
    rels3 = list(rels1)

    pkg1 = SnapshotDataPackage(
        snapshot_id=101,
        data_date=dd1,
        is_baseline=True,
        source_filename="PHX3DC1_20260101.xer",
        activities=acts1,
        relationships=rels1,
        calendars=cal,
        options=CPMOptions(data_date=dd1),
        project_late_anchors={1: datetime(2026, 4, 1, 17, 0)},
    )
    pkg2 = SnapshotDataPackage(
        snapshot_id=102,
        data_date=dd2,
        is_baseline=False,
        source_filename="PHX3DC1_20260201.xer",
        activities=acts2,
        relationships=rels2,
        calendars=cal,
        options=CPMOptions(data_date=dd2),
        project_late_anchors={1: datetime(2026, 4, 1, 17, 0)},
    )
    pkg3 = SnapshotDataPackage(
        snapshot_id=103,
        data_date=dd3,
        is_baseline=False,
        source_filename="PHX3DC1_20260301.xer",
        activities=acts3,
        relationships=rels3,
        calendars=cal,
        options=CPMOptions(data_date=dd3),
        project_late_anchors={1: datetime(2026, 4, 1, 17, 0)},
    )

    result = aggregate_historical_trends(
        project_id=1,
        snapshots=[pkg1, pkg2, pkg3],
    )

    print("=== HISTORICAL TREND AGGREGATION OUTPUT ===")
    print(f"Project ID: {result.project_id}")
    print(f"Total Snapshots Ingested: {result.total_snapshots}")
    print(f"Snapshots Order: {[s.data_date.strftime('%Y-%m-%d') for s in result.snapshots]}")
    print("\n--- DCMA 14-Point Trend Summary ---")
    for d in result.dcma_history:
        print(f"  Snapshot {d.snapshot_id} ({d.data_date.strftime('%Y-%m-%d')}): Overall Health = {d.overall_health_score:.1f}% | Missing Logic = {d.logic_missing_predecessors_count} | Neg Float Tasks = {d.negative_float_activities_count} | Hard Constraints = {d.hard_constraints_count}")

    print("\n--- Milestone Cumulative Slippages ---")
    for m in result.milestone_trends:
        print(f"  Milestone {m.task_code} ({m.milestone_name}): Net Slippage = {m.net_cumulative_slippage_days:.1f}d")
        for pt in m.history:
            ef_str = pt.early_finish.strftime('%Y-%m-%d') if pt.early_finish else 'N/A'
            print(f"    - Snap {pt.snapshot_id} ({pt.data_date.strftime('%Y-%m-%d')}): Finish = {ef_str}, Float = {pt.total_float_days}d, Cumulative Slippage = {pt.cumulative_slippage_days:.1f}d")

    print("\n--- Activity Float Progression (Zero Extrapolation) ---")
    for fl in result.driver_float_trends:
        print(f"  Activity {fl.task_code}:")
        for pt in fl.history:
            print(f"    - Snap {pt.snapshot_id} ({pt.data_date.strftime('%Y-%m-%d')}): Total Float = {pt.total_float_days}d")

    print("\n--- Sequential Driver Churn ---")
    for ch in result.driver_churn_progression:
        print(f"  Diff Snap {ch.from_snapshot_id} -> Snap {ch.to_snapshot_id} ({ch.to_data_date.strftime('%Y-%m-%d')}):")
        print(f"    * New Drivers: {ch.churn.new_drivers}")
        print(f"    * Persistent Drivers: {ch.churn.persistent_drivers}")
        print(f"    * Resolved Drivers: {ch.churn.resolved_drivers}")

    return result

if __name__ == "__main__":
    run_multi_snapshot_test()
