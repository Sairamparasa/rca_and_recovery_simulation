"""
Grounded Narrative Report Generator.
Generates plain-language executive project summaries, DCMA health assessments,
and driver diagnostics grounded strictly against deterministic calculations.
Propagates certainty tiers and explicitly formats unresolved driver hypotheses.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from arth_rca.reasoning.types import NarrativeReportPayload, CertaintyTier, EvidenceLedgerEntry
from arth_rca.reasoning.evidence_ledger import EvidenceLedger
from arth_rca.reasoning.llm_client import GroqClient
from arth_rca.analytics.driver_detection import DriverAnalysisResult
from arth_rca.analytics.dcma import DCMAAssessmentReport
from arth_rca.analytics.snapshot_diff import SnapshotDiffResult
from arth_rca.analytics.trend import HistoricalTrendPayload


REPORT_SYSTEM_PROMPT = """You are an expert Project Controls CPM Specialist and Schedule Forensic Analyst.
You generate executive narrative reports based EXCLUSIVELY on structured facts provided in the prompt.

CRITICAL RULES:
1. ZERO NUMBER INVENTION: You MUST NOT invent, approximate, calculate, or extrapolate ANY numbers, dates, float values, activity counts, or percentages. Every numeric value in your response MUST come directly from the Facts JSON.
2. CERTAINTY TIER PROPAGATION: Prefix every major factual assertion or section bullet with its epistemic certainty tier:
   - [FACT]: For explicit schedule properties (data dates, activity durations, status, explicit constraints).
   - [INFERENCE]: For deterministic CPM results (total float values, driving paths, driver blast radius counts).
   - [MODELED]: For heuristic classifications or impact scores.
   - [SIMULATION_DEPENDENT]: For what-if simulation outcomes.
   - [HYPOTHESIS]: For unresolved root causes requiring human PM validation.
3. UNRESOLVED DRIVERS: Whenever a driver root cause is 'unresolved', you MUST format it as a distinct callout:
   `> [!WARNING] **HYPOTHESIS (Requires PM Review)**: [hypothesized reason]`
4. FORMAT: Return structured GitHub-flavored markdown with clean headers, bullet points, and tables where appropriate.
"""


def generate_grounded_narrative_report(
    snapshot_id: int,
    data_date: datetime,
    project_name: str,
    driver_result: DriverAnalysisResult,
    dcma_report: DCMAAssessmentReport,
    diff_result: Optional[SnapshotDiffResult] = None,
    trend_payload: Optional[HistoricalTrendPayload] = None,
    llm_client: Optional[GroqClient] = None,
) -> NarrativeReportPayload:
    """
    Generates a structured, grounded narrative report for a snapshot.
    """
    client = llm_client or GroqClient()
    ledger = EvidenceLedger()

    # 1. Populate Evidence Ledger with deterministic facts
    ledger.record_fact(
        claim_text=f"Snapshot data date is {data_date.strftime('%Y-%m-%d')}",
        source_entity=f"Snapshot#{snapshot_id}",
        metric_name="data_date",
        metric_value=data_date.strftime('%Y-%m-%d'),
    )
    ledger.record_fact(
        claim_text=f"DCMA overall schedule health score is {dcma_report.overall_health_score}%",
        source_entity=f"DCMA#{snapshot_id}",
        metric_name="overall_health_score",
        metric_value=dcma_report.overall_health_score,
    )
    ledger.record_inference(
        claim_text=f"Total negative float activities: {driver_result.total_negative_float_activities}",
        source_entity=f"DriverAnalysis#{snapshot_id}",
        metric_name="total_negative_float_activities",
        metric_value=driver_result.total_negative_float_activities,
    )
    ledger.record_inference(
        claim_text=f"Distinct driver heads identified: {driver_result.driver_head_count}",
        source_entity=f"DriverAnalysis#{snapshot_id}",
        metric_name="driver_head_count",
        metric_value=driver_result.driver_head_count,
    )

    # 2. Build structured fact sheet for LLM context
    top_drivers_facts = []
    unresolved_hypotheses = []

    for d in driver_result.drivers[:8]:
        d_name = getattr(d, "driver_name", None) or d.driver_task_code
        chain_len = getattr(d, "downstream_activity_count", len(getattr(d, "blast_radius_nodes", [])))
        rc_desc = getattr(d, "root_cause_description", getattr(d, "root_cause_summary", ""))
        d_fact = {
            "driver_task_code": d.driver_task_code,
            "driver_name": d_name,
            "total_float_days": round(d.driver_total_float_days, 1),
            "impacted_downstream_count": chain_len,
            "root_cause_type": d.root_cause_type,
            "root_cause_summary": rc_desc,
            "is_convergence_head": getattr(d, "is_convergence_head", False),
            "impact_score": round(d.impact_score, 1),
        }
        top_drivers_facts.append(d_fact)

        if d.root_cause_type == "unresolved":
            unresolved_hypotheses.append({
                "task_code": d.driver_task_code,
                "task_name": d_name,
                "float_days": round(d.driver_total_float_days, 1),
                "hypothesis": rc_desc or "Unresolved delay pattern requiring PM investigation",
                "certainty_tier": CertaintyTier.HYPOTHESIS,
            })
            ledger.record_hypothesis(
                claim_text=f"Driver {d.driver_task_code} root cause is unverified/unresolved",
                source_entity=f"Activity#{d.driver_task_code}",
                metric_name="root_cause_type",
                metric_value="unresolved",
            )
        else:
            ledger.record_inference(
                claim_text=f"Driver {d.driver_task_code} has {round(d.driver_total_float_days, 1)}d float impacting {chain_len} activities",
                source_entity=f"Activity#{d.driver_task_code}",
                metric_name="total_float_days",
                metric_value=round(d.driver_total_float_days, 1),
            )

    dcma_metrics_facts = []
    for m in dcma_report.metrics:
        dcma_metrics_facts.append({
            "check_number": m.check_number,
            "name": m.name,
            "target_threshold": m.target_threshold,
            "actual_value": round(m.actual_value, 2) if isinstance(m.actual_value, float) else m.actual_value,
            "passed": m.passed,
            "failing_count": m.failing_activity_count,
        })
        ledger.record_fact(
            claim_text=f"DCMA Check #{m.check_number} ({m.name}): {m.actual_value} (target: {m.target_threshold})",
            source_entity=f"DCMA#Check{m.check_number}",
            metric_name=m.name,
            metric_value=m.actual_value,
        )

    facts_payload = {
        "project_name": project_name,
        "snapshot_id": snapshot_id,
        "data_date": data_date.strftime("%Y-%m-%d"),
        "dcma_overall_health_score": dcma_report.overall_health_score,
        "total_negative_float_tasks": driver_result.total_negative_float_activities,
        "total_driver_heads": driver_result.driver_head_count,
        "convergence_nodes": driver_result.convergence_nodes,
        "top_drivers": top_drivers_facts,
        "dcma_checks": dcma_metrics_facts,
    }

    if diff_result:
        facts_payload["diff"] = {
            "prior_snapshot_data_date": diff_result.snapshot_a_data_date.strftime("%Y-%m-%d") if diff_result.snapshot_a_data_date else None,
            "added_activities": diff_result.added_activities_count,
            "removed_activities": diff_result.removed_activities_count,
            "modified_activities": diff_result.modified_activities_count,
            "added_relationships": diff_result.added_relationships_count,
            "removed_relationships": diff_result.removed_relationships_count,
            "new_drivers": diff_result.driver_churn.new_drivers,
            "resolved_drivers": diff_result.driver_churn.resolved_drivers,
            "persistent_drivers": diff_result.driver_churn.persistent_drivers,
            "project_finish_slippage_days": round(diff_result.project_finish_slippage_days, 1),
        }

    # 3. Prompt LLM for structured sections
    user_prompt = f"""Write a comprehensive executive narrative report using the following facts JSON:

```json
{json.dumps(facts_payload, indent=2)}
```

Structure your report into 3 distinct sections:
1. ## Executive Summary
2. ## Schedule Health & DCMA 14-Point Assessment
3. ## Critical Path Drivers & Root-Cause Diagnostics
"""

    raw_report = client.generate(
        system_prompt=REPORT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=2000,
    )

    # 4. Fallback formatting if raw response is minimal or invalid
    fallback_exec = f"[FACT] Snapshot data date: {data_date.strftime('%Y-%m-%d')}. [INFERENCE] Total negative float activities: {driver_result.total_negative_float_activities} across {driver_result.driver_head_count} primary driver heads. [FACT] Overall DCMA Health Score is {dcma_report.overall_health_score}%."
    fallback_dcma = f"[FACT] Schedule Health Score: {dcma_report.overall_health_score}%. {len([m for m in dcma_report.metrics if not m.passed])} out of 14 checks flagged compliance issues."
    fallback_driver = f"[INFERENCE] Top driver head {top_drivers_facts[0]['driver_task_code'] if top_drivers_facts else 'N/A'} carries {top_drivers_facts[0]['total_float_days'] if top_drivers_facts else 0.0}d float and impacts {top_drivers_facts[0]['impacted_downstream_count'] if top_drivers_facts else 0} downstream tasks."

    exec_summary = fallback_exec
    dcma_narrative = fallback_dcma
    driver_narrative = fallback_driver

    if "## Executive Summary" in raw_report:
        parts = raw_report.split("## ")
        for p in parts:
            if p.startswith("Executive Summary"):
                exec_summary = p.replace("Executive Summary", "").strip()
            elif p.startswith("Schedule Health"):
                dcma_narrative = p.replace("Schedule Health & DCMA 14-Point Assessment", "").strip()
            elif p.startswith("Critical Path"):
                driver_narrative = p.replace("Critical Path Drivers & Root-Cause Diagnostics", "").strip()

    # Structural Runtime Grounding Validation
    from arth_rca.reasoning.grounding_validator import validate_and_sanitize_grounding
    ledger_entries = ledger.get_entries()

    v_exec = validate_and_sanitize_grounding(exec_summary, ledger_entries, "executive_summary", fallback_deterministic_text=fallback_exec)
    v_dcma = validate_and_sanitize_grounding(dcma_narrative, ledger_entries, "dcma_health", fallback_deterministic_text=fallback_dcma)
    v_driver = validate_and_sanitize_grounding(driver_narrative, ledger_entries, "drivers_diagnostic", fallback_deterministic_text=fallback_driver)

    exec_summary = v_exec.sanitized_text
    dcma_narrative = v_dcma.sanitized_text
    driver_narrative = v_driver.sanitized_text

    trends_narrative = None
    if diff_result:
        fallback_trends = (
            f"[FACT] Compared to prior snapshot ({diff_result.snapshot_a_data_date.strftime('%Y-%m-%d') if diff_result.snapshot_a_data_date else 'Baseline'}), "
            f"[INFERENCE] Net project finish slippage is {round(diff_result.project_finish_slippage_days, 1)} days. "
            f"[FACT] Modifications: {diff_result.modified_activities_count} activities modified, {diff_result.added_relationships_count} relationships added. "
            f"[INFERENCE] Driver churn: {len(diff_result.driver_churn.new_drivers)} new, {len(diff_result.driver_churn.resolved_drivers)} resolved, {len(diff_result.driver_churn.persistent_drivers)} persistent."
        )
        v_trends = validate_and_sanitize_grounding(fallback_trends, ledger_entries, "trends", fallback_deterministic_text=fallback_trends)
        trends_narrative = v_trends.sanitized_text

    return NarrativeReportPayload(
        snapshot_id=snapshot_id,
        data_date=data_date,
        project_name=project_name,
        executive_summary=exec_summary,
        dcma_health_narrative=dcma_narrative,
        critical_path_and_drivers_narrative=driver_narrative,
        snapshot_trends_narrative=trends_narrative,
        evidence_ledger=ledger_entries,
        unresolved_hypotheses=unresolved_hypotheses,
    )
