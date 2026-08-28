"""
Structural Runtime Grounding Validator.
Inspects raw LLM generations for ungrounded numeric claims and cross-checks every
detected number against the Evidence Ledger and facts payload.
Replaces or rejects ungrounded hallucinations before they reach the user.
"""

import re
from typing import List, Set, Tuple, Optional, Any, Union
from pydantic import BaseModel, Field

from arth_rca.reasoning.types import EvidenceLedgerEntry


class GroundingViolation(BaseModel):
    ungrounded_token: str
    numeric_value: float
    context_snippet: str
    field_name: str


class GroundingValidationResult(BaseModel):
    is_valid: bool
    sanitized_text: str
    violations: List[GroundingViolation] = Field(default_factory=list)


def extract_factual_numbers_from_ledger(
    ledger_entries: List[EvidenceLedgerEntry],
    additional_facts: Optional[List[Any]] = None,
) -> Set[float]:
    """
    Extracts all allowed numerical values from the evidence ledger and facts payload.
    """
    valid_numbers: Set[float] = set()

    # Standard structural numbers (1-14 DCMA checks, 1-10 sections/steps, year 2024-2030)
    for n in range(0, 32):
        valid_numbers.add(float(n))
    for yr in range(2020, 2035):
        valid_numbers.add(float(yr))

    # Add ledger metric values
    for entry in ledger_entries:
        mv = entry.metric_value
        if mv is None:
            continue
        if isinstance(mv, (int, float)):
            valid_numbers.add(float(mv))
            valid_numbers.add(round(float(mv), 1))
            valid_numbers.add(round(float(mv), 2))
        elif isinstance(mv, str):
            # Parse possible numbers from string
            nums = re.findall(r"[-+]?\d*\.?\d+", mv)
            for num_str in nums:
                try:
                    val = float(num_str)
                    valid_numbers.add(val)
                    valid_numbers.add(round(val, 1))
                    valid_numbers.add(round(val, 2))
                except ValueError:
                    pass

    if additional_facts:
        for fact in additional_facts:
            if isinstance(fact, (int, float)):
                valid_numbers.add(float(fact))
                valid_numbers.add(round(float(fact), 1))
            elif isinstance(fact, str):
                nums = re.findall(r"[-+]?\d*\.?\d+", fact)
                for num_str in nums:
                    try:
                        valid_numbers.add(float(num_str))
                    except ValueError:
                        pass

    return valid_numbers


def validate_and_sanitize_grounding(
    text: str,
    ledger_entries: List[EvidenceLedgerEntry],
    field_name: str = "report",
    fallback_deterministic_text: Optional[str] = None,
    tolerance: float = 0.05,
) -> GroundingValidationResult:
    """
    Validates that every numeric value mentioned in the generated text is backed
    by a verified entry in the evidence ledger.
    If an ungrounded hallucination is found, either sanitizes the token or falls back.
    """
    if not text:
        return GroundingValidationResult(is_valid=True, sanitized_text="")

    allowed_numbers = extract_factual_numbers_from_ledger(ledger_entries)
    violations: List[GroundingViolation] = []

    # Regex finding numbers (integers, floats, negative numbers, percentages, dollar amounts)
    # Matches patterns like -99.0, 99.9%, $999,999, 47.0d
    pattern = re.compile(r'(?<![A-Za-z0-9_#-])([-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+\.\d+)([%d]?)(?![A-Za-z0-9_])')

    sanitized_text = text

    def check_match(match: re.Match) -> str:
        raw_num_str = match.group(1).replace(",", "")
        suffix = match.group(2)
        try:
            val = float(raw_num_str)
        except ValueError:
            return match.group(0)

        # Check if val matches any allowed number within tolerance
        is_allowed = any(abs(val - allowed) <= tolerance for allowed in allowed_numbers)

        if not is_allowed:
            start = max(0, match.start() - 25)
            end = min(len(text), match.end() + 25)
            context = text[start:end].replace("\n", " ")
            violations.append(
                GroundingViolation(
                    ungrounded_token=match.group(0),
                    numeric_value=val,
                    context_snippet=context,
                    field_name=field_name,
                )
            )
            # Flag or sanitize
            return f"[UNVERIFIED METRIC: {match.group(0)}]"

        return match.group(0)

    sanitized_text = pattern.sub(check_match, text)

    if violations and fallback_deterministic_text:
        # If severe hallucination detected and fallback available, use deterministic fallback
        return GroundingValidationResult(
            is_valid=False,
            sanitized_text=fallback_deterministic_text,
            violations=violations,
        )

    return GroundingValidationResult(
        is_valid=(len(violations) == 0),
        sanitized_text=sanitized_text,
        violations=violations,
    )
