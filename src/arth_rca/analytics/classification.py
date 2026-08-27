"""
Relationship Constraint Classification Engine.
Determines Hard vs. Soft FS logic for fast-track recovery simulation per Section 5 of Complete_Implementation_Plan.md.
"""

import re
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
from pydantic import BaseModel

from arth_rca.analytics.classification_config import (
    AUTO_CLASSIFY_THRESHOLD,
    HARD_REGULATORY_TERMS,
    HARD_SAFETY_TERMS,
    HARD_PHYSICAL_TERMS,
    CURING_LAG_BANDS_HOURS,
)
from arth_rca.cpm.types import CPMRelationshipInput
from arth_rca.db.models import (
    RelationshipClassification,
    ClassificationPattern,
    generate_relationship_key,
    utc_now,
)


class ClassificationResult(BaseModel):
    relationship_key: str
    pred_task_code: str
    succ_task_code: str
    relationship_type: str = "FS"
    lag_days: float = 0.0
    constraint_type: str = "UNCLASSIFIED"
    confidence: float = 0.0
    classification_source: str = "HEURISTIC_KEYWORD"
    rationale: str = ""
    is_auto_classified: bool = False
    needs_pm_review: bool = True
    library_pattern_id: Optional[int] = None
    longest_path_distance: Optional[int] = None


def is_fasttrack_candidate(rel_classification: Any) -> bool:
    """
    Hard programmatic gate for the What-If Recovery Engine.
    Strictly permits fast-track (FS->SS or lag reduction) ONLY if classified as SOFT_RESOURCE
    or SOFT_COORDINATION with confidence >= AUTO_CLASSIFY_THRESHOLD or PM_REVIEWED.
    Never allows UNCLASSIFIED, HARD_PHYSICAL, HARD_REGULATORY, or HARD_SAFETY.
    """
    ctype = getattr(rel_classification, "constraint_type", "UNCLASSIFIED")
    conf = getattr(rel_classification, "confidence", 0.0)
    source = getattr(rel_classification, "classification_source", "")

    if ctype in ("HARD_PHYSICAL", "HARD_REGULATORY", "HARD_SAFETY", "UNCLASSIFIED"):
        return False

    if source == "PM_REVIEWED":
        return ctype in ("SOFT_RESOURCE", "SOFT_COORDINATION")

    return ctype in ("SOFT_RESOURCE", "SOFT_COORDINATION") and conf >= AUTO_CLASSIFY_THRESHOLD


def _contains_word_boundary_term(text: str, terms: List[str]) -> Optional[str]:
    """Check if any term from terms matches text using word boundaries."""
    if not text:
        return None
    lower_text = text.lower()
    for term in terms:
        # Match term on word boundaries
        pattern = rf"\b{re.escape(term.lower())}\b" if len(term.split()) == 1 else re.escape(term.lower())
        if re.search(pattern, lower_text):
            return term
    return None


def _extract_csi_division(task_code: str, task_name: str) -> Optional[int]:
    """Extract CSI MasterFormat 2-digit division from task code or name (e.g., 03-3000 -> 3)."""
    m = re.search(r"\b(0[1-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9])\b", f"{task_code} {task_name}")
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def classify_relationship(
    pred_task_code: str,
    pred_task_name: str,
    succ_task_code: str,
    succ_task_name: str,
    rel_type: str = "FS",
    lag_days: float = 0.0,
    patterns: Optional[List[ClassificationPattern]] = None,
    existing_classification: Optional[RelationshipClassification] = None,
    previous_lag_days: Optional[float] = None,
    threshold: float = AUTO_CLASSIFY_THRESHOLD,
) -> ClassificationResult:
    """
    Classify a single relationship using the deterministic priority stack:
    1. Carry forward PM_REVIEWED classifications (unless lag changed >25%).
    2. Library Pattern match.
    3. Regulatory keyword match (Confidence = 0.90) -> HARD_REGULATORY.
    4. Safety keyword match (Confidence = 0.90) -> HARD_SAFETY.
    5. Physical/curing keyword match (Confidence = 0.85) -> HARD_PHYSICAL (+0.15 lag boost).
    6. CSI division jump (+0.10 supporting signal).
    7. Same-trade/same-crew (Confidence = 0.55) -> SOFT_RESOURCE (below threshold, for PM queue).
    8. Default -> UNCLASSIFIED.
    """
    rel_key = generate_relationship_key(pred_task_code, succ_task_code, rel_type)
    lag_hrs = lag_days * 8.0

    # 1. Check existing PM_REVIEWED classification
    if existing_classification and existing_classification.classification_source == "PM_REVIEWED":
        # Trigger re-review if lag changed by > 25%
        if previous_lag_days is not None and previous_lag_days > 0.0:
            lag_delta_pct = abs(lag_days - previous_lag_days) / previous_lag_days
            if lag_delta_pct > 0.25:
                return ClassificationResult(
                    relationship_key=rel_key,
                    pred_task_code=pred_task_code,
                    succ_task_code=succ_task_code,
                    relationship_type=rel_type,
                    lag_days=lag_days,
                    constraint_type="UNCLASSIFIED",
                    confidence=0.5,
                    classification_source="PM_REVIEW_REQUIRED_LAG_CHANGE",
                    rationale=f"Previous PM classification flagged for re-review: lag changed by {lag_delta_pct*100:.1f}% (was {previous_lag_days}d, now {lag_days}d).",
                    is_auto_classified=False,
                    needs_pm_review=True,
                )

        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type=existing_classification.constraint_type,
            confidence=existing_classification.confidence,
            classification_source="PM_REVIEWED",
            rationale=existing_classification.rationale or "Carried forward from PM review.",
            is_auto_classified=True,
            needs_pm_review=False,
        )

    # 2. Check Reusable Library Patterns
    if patterns:
        for pat in patterns:
            pred_match = re.search(pat.predecessor_pattern, f"{pred_task_code} {pred_task_name}", re.IGNORECASE)
            succ_match = re.search(pat.successor_pattern, f"{succ_task_code} {succ_task_name}", re.IGNORECASE)
            if pred_match and succ_match:
                if pat.min_lag_hrs is None or lag_hrs >= pat.min_lag_hrs:
                    return ClassificationResult(
                        relationship_key=rel_key,
                        pred_task_code=pred_task_code,
                        succ_task_code=succ_task_code,
                        relationship_type=rel_type,
                        lag_days=lag_days,
                        constraint_type=pat.constraint_type,
                        confidence=0.95,
                        classification_source="LIBRARY_MATCH",
                        rationale=f"Matched library pattern #{pat.id} ('{pat.predecessor_pattern}' -> '{pat.successor_pattern}').",
                        is_auto_classified=True,
                        needs_pm_review=False,
                        library_pattern_id=pat.id,
                    )

    # Combined text inspection
    combined_pred = f"{pred_task_code} {pred_task_name}".lower()
    combined_succ = f"{succ_task_code} {succ_task_name}".lower()

    # 3. Regulatory Keywords Match (Confidence = 0.90) -> Outranks soft signals
    reg_term_pred = _contains_word_boundary_term(combined_pred, HARD_REGULATORY_TERMS)
    reg_term_succ = _contains_word_boundary_term(combined_succ, HARD_REGULATORY_TERMS)
    if reg_term_pred or reg_term_succ:
        matched_term = reg_term_pred or reg_term_succ
        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type="HARD_REGULATORY",
            confidence=0.90,
            classification_source="HEURISTIC_KEYWORD",
            rationale=f"Regulatory/inspection keyword detected: '{matched_term}'.",
            is_auto_classified=True,
            needs_pm_review=False,
        )

    # 4. Safety Keywords Match (Confidence = 0.90) -> Outranks soft signals
    safety_term_pred = _contains_word_boundary_term(combined_pred, HARD_SAFETY_TERMS)
    safety_term_succ = _contains_word_boundary_term(combined_succ, HARD_SAFETY_TERMS)
    if safety_term_pred or safety_term_succ:
        matched_term = safety_term_pred or safety_term_succ
        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type="HARD_SAFETY",
            confidence=0.90,
            classification_source="HEURISTIC_KEYWORD",
            rationale=f"Safety/isolation keyword detected: '{matched_term}'.",
            is_auto_classified=True,
            needs_pm_review=False,
        )

    # 5. Physical / Curing Keywords Match (Confidence = 0.85)
    phys_term_pred = _contains_word_boundary_term(combined_pred, HARD_PHYSICAL_TERMS)
    phys_term_succ = _contains_word_boundary_term(combined_succ, HARD_PHYSICAL_TERMS)
    if phys_term_pred or phys_term_succ:
        matched_term = phys_term_pred or phys_term_succ
        conf = 0.85
        rationale = f"Physical curing/setting keyword detected: '{matched_term}'."

        # Check Lag-Duration Correlation (+0.15 boost)
        for band_name, (min_h, max_h) in CURING_LAG_BANDS_HOURS.items():
            if min_h <= lag_hrs <= max_h:
                conf = min(0.95, conf + 0.15)
                rationale += f" Supporting lag correlation: {lag_hrs}h falls in {band_name} band ({min_h}-{max_h}h)."
                break

        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type="HARD_PHYSICAL",
            confidence=conf,
            classification_source="HEURISTIC_KEYWORD",
            rationale=rationale,
            is_auto_classified=conf >= threshold,
            needs_pm_review=conf < threshold,
        )

    # 6. CSI Division Jump (Supporting signal +0.10 toward HARD_PHYSICAL)
    pred_div = _extract_csi_division(pred_task_code, pred_task_name)
    succ_div = _extract_csi_division(succ_task_code, succ_task_name)
    if pred_div and succ_div and abs(succ_div - pred_div) >= 4:
        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type="HARD_PHYSICAL",
            confidence=0.60,
            classification_source="HEURISTIC_CSI_JUMP",
            rationale=f"Major CSI MasterFormat division jump detected: Div {pred_div:02d} -> Div {succ_div:02d}.",
            is_auto_classified=False,
            needs_pm_review=True,
        )

    # 7. Same-Trade / Same-Crew Heuristic -> Suggests SOFT_RESOURCE (Confidence = 0.55)
    pred_prefix = pred_task_code.split("-")[0].strip().upper() if "-" in pred_task_code else pred_task_code[:3].upper()
    succ_prefix = succ_task_code.split("-")[0].strip().upper() if "-" in succ_task_code else succ_task_code[:3].upper()
    if pred_prefix and succ_prefix and pred_prefix == succ_prefix:
        return ClassificationResult(
            relationship_key=rel_key,
            pred_task_code=pred_task_code,
            succ_task_code=succ_task_code,
            relationship_type=rel_type,
            lag_days=lag_days,
            constraint_type="SOFT_RESOURCE",
            confidence=0.55,
            classification_source="HEURISTIC_KEYWORD",
            rationale=f"Same-trade / discipline prefix '{pred_prefix}' suggests resource handoff sequence.",
            is_auto_classified=False,
            needs_pm_review=True,
        )

    # 8. Unclassified Fallback
    return ClassificationResult(
        relationship_key=rel_key,
        pred_task_code=pred_task_code,
        succ_task_code=succ_task_code,
        relationship_type=rel_type,
        lag_days=lag_days,
        constraint_type="UNCLASSIFIED",
        confidence=0.0,
        classification_source="UNCLASSIFIED",
        rationale="No physical, regulatory, or pattern heuristics matched. Queued for PM review.",
        is_auto_classified=False,
        needs_pm_review=True,
    )
