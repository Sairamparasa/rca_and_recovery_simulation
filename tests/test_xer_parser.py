"""
Unit tests for the XER Parser and Validator.
"""

import pytest
from pathlib import Path

from arth_rca.parser.xer_parser import XERParser, XERParserError
from arth_rca.parser.validator import XERValidator, XERValidationError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parser_loads_standard_fixture():
    parser = XERParser()
    parsed = parser.parse_file(FIXTURES_DIR / "fixture_standard_cpm.xer")

    assert len(parsed.projects) == 1
    assert len(parsed.calendars) == 1
    assert len(parsed.tasks) == 6
    assert len(parsed.predecessors) == 6

    task_a100 = next(t for t in parsed.tasks.values() if t.task_code == "A100")
    assert task_a100.target_durn_hr_cnt == 16.0
    assert task_a100.task_name == "Site Mobilization"


def test_validator_succeeds_on_valid_fixture():
    parser = XERParser()
    validator = XERValidator()
    
    parsed = parser.parse_file(FIXTURES_DIR / "fixture_standard_cpm.xer")
    res = validator.validate(parsed, strict=True)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validator_rejects_malformed_corrupt_xer():
    parser = XERParser()
    validator = XERValidator()

    parsed = parser.parse_file(FIXTURES_DIR / "malformed_corrupt.xer")
    with pytest.raises(XERValidationError) as exc_info:
        validator.validate(parsed, strict=True)

    assert "Missing required table" in str(exc_info.value)
    assert "Orphaned relationship" in str(exc_info.value)


def test_parser_rejects_invalid_header():
    parser = XERParser()
    with pytest.raises(XERParserError) as exc_info:
        parser.parse_content("INVALID_HEADER\n%T\tPROJECT\n")
    assert "Invalid XER header" in str(exc_info.value)
