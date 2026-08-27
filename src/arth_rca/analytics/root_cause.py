"""
Deterministic Root-Cause Typing Engine.
Categorizes driver heads strictly into deterministic classifications:
- constraint: Hard/late constraint forcing date or negative float
- out_of_sequence: In-progress/completed with unstarted/uncompleted predecessors (or Progress Override execution)
- logic_change: Relationship added or modified between snapshots
- external_delay: Actual duration exceeded planned duration or calendar delay
- unresolved: Fallback when no single deterministic rule applies cleanly (avoids guessing)
"""

from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel
from datetime import datetime

from arth_rca.cpm.types import CPMActivityResult


class RootCauseResult(BaseModel):
    task_id: int
    task_code: str
    category: str  # constraint | out_of_sequence | logic_change | external_delay | unresolved
    confidence_score: float  # 1.0 for deterministic match
    summary: str
    evidence_details: Dict[str, Any]


HARD_CONSTRAINTS = {"CS_MANDSTART", "CS_MSTART", "CS_MANDEND", "CS_MANDFIN", "CS_MEND", "CS_FSB", "CS_FNLT", "CS_MSOB", "CS_SNLT"}


def classify_driver_root_cause(
    driver_task_id: int,
    raw_task: any,
    cpm_act_result: CPMActivityResult,
    predecessors: List[any],
    all_raw_tasks: Dict[int, any],
    baseline_task: Optional[any] = None,
    previous_snapshot_relationships: Optional[List[any]] = None,
) -> RootCauseResult:
    """
    Deterministic evaluation of driver head root causes per Section 4.2 rules.
    """
    task_code = getattr(raw_task, "task_code", str(driver_task_id))
    cstr_type = getattr(raw_task, "cstr_type", None)
    cstr_date = getattr(raw_task, "cstr_date", None)
    status_code = getattr(raw_task, "status_code", "TK_NotStart")

    # 1. Check Constraint Rule:
    # If the activity has a hard or late constraint that directly restricts dates or imposes negative float
    if cstr_type in HARD_CONSTRAINTS and cstr_date:
        return RootCauseResult(
            task_id=driver_task_id,
            task_code=task_code,
            category="constraint",
            confidence_score=1.0,
            summary=f"Hard/Late constraint '{cstr_type}' applied on {cstr_date.strftime('%Y-%m-%d')}.",
            evidence_details={"cstr_type": cstr_type, "cstr_date": str(cstr_date)},
        )

    # 2. Check Out-of-Sequence Rule:
    # If the activity is Active or Complete, but has uncompleted predecessors
    if status_code in ("TK_Active", "TK_Complete"):
        uncompleted_preds = []
        for p in predecessors:
            pred_id = getattr(p, "pred_task_id", None)
            pred_task = all_raw_tasks.get(pred_id)
            if pred_task and getattr(pred_task, "status_code", "") != "TK_Complete":
                uncompleted_preds.append(getattr(pred_task, "task_code", str(pred_id)))

        if uncompleted_preds:
            return RootCauseResult(
                task_id=driver_task_id,
                task_code=task_code,
                category="out_of_sequence",
                confidence_score=1.0,
                summary=f"Out-of-sequence execution: started/active while predecessors ({', '.join(uncompleted_preds[:3])}) remain uncompleted.",
                evidence_details={"uncompleted_predecessors": uncompleted_preds},
            )

    # 3. Check External Delay / Duration Variance Rule:
    # If target duration or remaining duration increased significantly past baseline
    if baseline_task:
        target_durn = getattr(raw_task, "target_durn_hr_cnt", 0.0)
        base_durn = getattr(baseline_task, "target_durn_hr_cnt", 0.0)
        if target_durn > base_durn:
            durn_delta_days = (target_durn - base_durn) / 8.0
            return RootCauseResult(
                task_id=driver_task_id,
                task_code=task_code,
                category="external_delay",
                confidence_score=1.0,
                summary=f"Duration expansion: Target duration increased by {durn_delta_days:.1f} days past baseline.",
                evidence_details={"baseline_days": base_durn / 8.0, "current_days": target_durn / 8.0, "delta_days": durn_delta_days},
            )

    # 4. Check Logic Change Rule:
    # If previous snapshot relationship links are provided and a new driving link was added
    if previous_snapshot_relationships is not None:
        prev_pred_ids = {getattr(p, "pred_task_id", None) for p in previous_snapshot_relationships if getattr(p, "succ_task_id", None) == driver_task_id}
        curr_pred_ids = {getattr(p, "pred_task_id", None) for p in predecessors if getattr(p, "succ_task_id", None) == driver_task_id}
        added_links = curr_pred_ids - prev_pred_ids
        if added_links:
            added_codes = [getattr(all_raw_tasks.get(pid), "task_code", str(pid)) for pid in added_links]
            return RootCauseResult(
                task_id=driver_task_id,
                task_code=task_code,
                category="logic_change",
                confidence_score=1.0,
                summary=f"Logic change: New predecessor relationship added ({', '.join(added_codes)}).",
                evidence_details={"added_predecessors": added_codes},
            )

    # 5. Deterministic fallback: unresolved
    return RootCauseResult(
        task_id=driver_task_id,
        task_code=task_code,
        category="unresolved",
        confidence_score=0.5,
        summary="No single deterministic root-cause rule applied cleanly; marked unresolved.",
        evidence_details={"status_code": status_code, "total_float_days": cpm_act_result.total_float_days},
    )
