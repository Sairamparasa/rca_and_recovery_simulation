"""
Adversarial Test: Injects deliberate LLM hallucinations (fabricated float numbers, fabricated percentages, fabricated costs)
and asserts that the system detects and rejects/sanitizes the ungrounded numbers.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from arth_rca.reasoning.llm_client import GroqClient
from arth_rca.reasoning.report_generator import generate_grounded_narrative_report
from arth_rca.analytics.driver_detection import DriverAnalysisResult, DrivingChainTree
from arth_rca.analytics.dcma import DCMAAssessmentReport, DCMAMetricResult

class MockAdversarialGroqClient(GroqClient):
    """
    Simulates a hallucinating LLM that injects fabricated numbers not present in the facts payload:
    - Hallucinated total float: -99.0d (real is -47.0d)
    - Hallucinated DCMA health score: 99.9% (real is 57.14%)
    - Hallucinated cost: $999,999 (not in facts)
    """
    def __init__(self, fabricated_text: str):
        super().__init__()
        self.fabricated_text = fabricated_text

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 1500) -> str:
        return self.fabricated_text


def test_adversarial_hallucination_detection():
    # Real deterministic data
    dd = datetime(2026, 3, 1)
    drivers = [
        DrivingChainTree(
            driver_task_id=1,
            driver_task_code="QTS-28981",
            driver_total_float_days=-47.0,
            root_cause_type="unresolved",
            root_cause_description="Long lead vendor submittal",
            impact_score=85.0,
            downstream_activity_count=5,
        )
    ]
    driver_res = DriverAnalysisResult(
        snapshot_id=103,
        data_date=dd,
        total_negative_float_activities=3,
        driver_head_count=1,
        drivers=drivers,
    )
    dcma_report = DCMAAssessmentReport(
        snapshot_id=103,
        data_date="2026-03-01",
        overall_health_score=57.14,
        passed_checks_count=8,
        failed_checks_count=6,
        metrics=[
            DCMAMetricResult(
                check_number=1,
                name="Logic Missing Predecessors",
                target_threshold="0.0%",
                actual_value=1.0,
                passed=False,
                failing_activity_count=1,
                total_applicable_count=4,
            )
        ],
    )

    # Hallucinated LLM response
    fabricated_markdown = """
## Executive Summary
[FACT] The project is progressing well with overall DCMA score of 99.9%. Critical path driver QTS-28981 has -99.0 days of total float.

## Schedule Health & DCMA 14-Point Assessment
[FACT] Health score is 99.9%.

## Critical Path Drivers & Root-Cause Diagnostics
[INFERENCE] Top driver is QTS-28981 with -99.0 days float.
"""

    mock_client = MockAdversarialGroqClient(fabricated_markdown)

    report = generate_grounded_narrative_report(
        snapshot_id=103,
        data_date=dd,
        project_name="PHX3DC1",
        driver_result=driver_res,
        dcma_report=dcma_report,
        llm_client=mock_client,
    )

    # 1. Verify that hallucinated numbers -99.0 and 99.9 are sanitized or rejected
    assert "-99.0" not in report.executive_summary, "Hallucinated -99.0d float was accepted in executive summary!"
    assert "99.9" not in report.executive_summary, "Hallucinated 99.9% health score was accepted in executive summary!"
    assert "-99.0" not in report.critical_path_and_drivers_narrative, "Hallucinated -99.0d float was accepted in driver narrative!"

    # 2. Verify that legitimate factual numbers (-47.0d float and 57.1% DCMA score) are preserved
    assert "-47.0" in report.executive_summary or "-47.0" in report.critical_path_and_drivers_narrative


def test_adversarial_recommendation_explainer():
    from arth_rca.optimization.models import ParetoPoint, OptimizationResult
    from arth_rca.reasoning.recommendations import explain_pareto_tradeoffs

    real_points = [
        ParetoPoint(
            scenario_name="Scenario #1",
            cost_delta=15000.0,
            days_recovered=10.0,
            simulated_finish_date="2026-10-01",
            remaining_discrete_delayed_count=3,
            discrete_delayed_recovered_count=2,
            critical_path_shifted=False,
            levers_applied=[],
        ),
        ParetoPoint(
            scenario_name="Scenario #2",
            cost_delta=45000.0,
            days_recovered=22.0,
            simulated_finish_date="2026-09-15",
            remaining_discrete_delayed_count=1,
            discrete_delayed_recovered_count=4,
            critical_path_shifted=True,
            levers_applied=[],
        ),
    ]

    # Adversarial LLM invents a fabricated scenario costing $999,999 recovering 150 days
    fabricated_text = "[SIMULATION_DEPENDENT] You should pick Scenario #99 which recovers 150.0 days for $999,999.00."
    mock_client = MockAdversarialGroqClient(fabricated_text)

    output = explain_pareto_tradeoffs(real_points, project_name="PHX3DC1", llm_client=mock_client)

    # Hallucinated values must NOT appear in output
    assert "999,999" not in output
    assert "150.0" not in output
    # Legitimate numbers ($15,000 and 10.0 days) must be present in sanitized output
    assert "15,000" in output
    assert "10.0" in output


def test_adversarial_nl_query():
    from sqlmodel import Session, SQLModel, create_engine
    from arth_rca.reasoning.nl_query import execute_nl_query
    from arth_rca.reasoning.types import NLQueryRequest
    from arth_rca.db.models import Project, Snapshot, Activity, Relationship

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as db:
        proj = Project(name="PHX3DC1", org_id="ORG1")
        db.add(proj)
        db.commit()
        db.refresh(proj)

        snap = Snapshot(project_id=proj.id, data_date=datetime(2026, 3, 1), source_filename="test.xer")
        db.add(snap)
        db.commit()
        db.refresh(snap)

        act = Activity(
            snapshot_id=snap.id,
            task_code="QTS-28981",
            name="Substation Feeder",
            status="IN_PROGRESS",
            total_float=-47.0,
            remaining_duration=45.0,
            original_duration=45.0,
        )
        db.add(act)
        db.commit()

        # Adversarial LLM invents a fabricated float value -123.4d and fabricated duration 888.0d
        fabricated_answer = "[INFERENCE] Activity QTS-28981 is delayed by -123.4 days with remaining duration of 888.0 days."
        mock_client = MockAdversarialGroqClient(fabricated_answer)

        req = NLQueryRequest(snapshot_id=snap.id, query="Why is QTS-28981 delayed?")
        res = execute_nl_query(req, db, llm_client=mock_client)

        # Hallucinated numbers must NOT appear
        assert "-123.4" not in res.answer_markdown
        assert "888.0" not in res.answer_markdown

        # Real grounded numbers (-47.0d float, 45.0d duration) must be present in sanitized output
        assert "-47.0" in res.answer_markdown
        assert "45.0" in res.answer_markdown



