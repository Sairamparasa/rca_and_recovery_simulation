"""
Validator for parsed XER files ensuring structural integrity and relational consistency.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from arth_rca.parser.xer_models import XERParsedFile


class XERValidationError(Exception):
    """Raised when XER contents fail structural, relational, or data-integrity validation."""
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class XERValidator:
    """Validates structural and relational integrity of parsed XER files."""

    REQUIRED_TABLES = ["PROJECT", "CALENDAR", "TASK"]

    def validate(self, parsed: XERParsedFile, strict: bool = True) -> ValidationResult:
        """
        Validate XER parsed data.
        Raises XERValidationError if strict is True and validation errors exist.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Required tables check
        for table in self.REQUIRED_TABLES:
            if table not in parsed.raw_tables or len(parsed.raw_tables[table]) == 0:
                errors.append(f"Missing required table or empty table: '{table}'")

        if not parsed.projects:
            errors.append("No valid project records found in PROJECT table.")

        if not parsed.tasks:
            errors.append("No valid task records found in TASK table.")

        # 2. Check task uniqueness and references
        task_ids = set(parsed.tasks.keys())
        calendar_ids = set(parsed.calendars.keys())
        wbs_ids = set(parsed.wbs.keys())

        # Check task calendar validity
        for task_id, task in parsed.tasks.items():
            if task.clndr_id and task.clndr_id not in calendar_ids:
                warnings.append(
                    f"Task '{task.task_code}' (id={task_id}) references non-existent calendar id {task.clndr_id}"
                )

        # 3. Check relationship integrity (orphaned predecessors/successors)
        for pred in parsed.predecessors:
            if pred.pred_task_id not in task_ids:
                errors.append(
                    f"Orphaned relationship: Predecessor task_id {pred.pred_task_id} not found in TASK table."
                )
            if pred.task_id not in task_ids:
                errors.append(
                    f"Orphaned relationship: Successor task_id {pred.task_id} not found in TASK table."
                )

        stats = {
            "projects_count": len(parsed.projects),
            "calendars_count": len(parsed.calendars),
            "tasks_count": len(parsed.tasks),
            "relationships_count": len(parsed.predecessors),
            "resources_count": len(parsed.resources),
            "wbs_count": len(parsed.wbs),
        }

        is_valid = len(errors) == 0
        result = ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            stats=stats,
        )

        if strict and not is_valid:
            error_summary = "; ".join(errors)
            raise XERValidationError(f"XER validation failed: {error_summary}", errors=errors)

        return result
