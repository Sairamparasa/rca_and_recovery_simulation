"""
Recommendation Framing & Pareto Trade-off Explainer.
Given optimization results and Pareto frontier scenarios, generates grounded qualitative
trade-off analyses explicitly citing scenario IDs, recovery days, and cost deltas.
"""

import json
from typing import List, Dict, Optional, Any, Union

from arth_rca.reasoning.types import ScenarioExplanationPayload, CertaintyTier
from arth_rca.reasoning.llm_client import GroqClient
from arth_rca.optimization.models import ParetoPoint, OptimizationResult


RECOMMENDATION_SYSTEM_PROMPT = """You are a Senior Project Manager and Schedule Recovery Advisor.
Your job is to analyze schedule optimization scenarios and explain the qualitative trade-offs between cost, days recovered, disruption, and risk.

MANDATORY RULES:
1. GROUNDING: Use the EXACT dollar costs, recovery days, and scenario IDs from the provided facts.
2. CITATION: Explicitly cite Scenario IDs (e.g. Scenario #1, Scenario #2) in every trade-off comparison.
3. CERTAINTY TIER: All scenario predictions are simulation-dependent; tag trade-off claims with `[SIMULATION_DEPENDENT]`.
4. ACTIONABLE GUIDANCE: Clearly contrast low-cost / quick-win options vs maximum-recovery / high-investment options.
"""


def explain_pareto_tradeoffs(
    frontier: Union[List[ParetoPoint], OptimizationResult, Any],
    project_name: str = "Project",
    llm_client: Optional[GroqClient] = None,
) -> str:
    """
    Generates an executive narrative explaining the Pareto frontier trade-offs across all non-dominated scenarios.
    """
    client = llm_client or GroqClient()

    points = frontier.pareto_frontier if hasattr(frontier, "pareto_frontier") else (frontier if isinstance(frontier, list) else getattr(frontier, "points", []))

    scenarios_fact_sheet = [
        {
            "scenario_id": idx + 1,
            "scenario_name": getattr(pt, "scenario_name", f"Scenario #{idx + 1}"),
            "cost_delta": round(pt.cost_delta, 2),
            "days_recovered": round(pt.days_recovered, 2),
            "project_finish_date": getattr(pt, "simulated_finish_date", str(getattr(pt, "project_finish_date", "N/A"))),
            "critical_path_shift": getattr(pt, "critical_path_shifted", getattr(pt, "critical_path_shift", False)),
            "levers_count": len(pt.levers_applied),
            "levers": pt.levers_applied,
        }
        for idx, pt in enumerate(points)
    ]

    facts_payload = {
        "project_name": project_name,
        "total_frontier_scenarios": len(points),
        "scenarios": scenarios_fact_sheet,
    }

    user_prompt = f"""Analyze the following Pareto Frontier schedule recovery scenarios:

```json
{json.dumps(facts_payload, indent=2)}
```

Write a structured executive recommendation framing:
1. Low-cost / initial recovery option (Scenario #1)
2. Maximum recovery option and budget requirement
3. Key operational trade-offs (overtime vs fast-tracking risk)
"""

    narrative = client.generate(
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=800,
    )

    # Build deterministic fallback
    lines = ["[SIMULATION_DEPENDENT] **Pareto Frontier Recovery Trade-Offs**:"]
    allowed_facts: List[Any] = []
    for s in scenarios_fact_sheet:
        allowed_facts.extend([s['scenario_id'], s['cost_delta'], s['days_recovered'], s['levers_count']])
        lines.append(
            f"- **Scenario #{s['scenario_id']}**: Recovers **{s['days_recovered']} days** for **${s['cost_delta']:,.2f}** "
            f"(Finish Date: {s['project_finish_date']}, Levers: {s['levers_count']})."
        )
    deterministic_fallback = "\n".join(lines)

    if "[Grounded Response" in narrative or len(narrative.strip()) < 10:
        narrative = deterministic_fallback

    from arth_rca.reasoning.grounding_validator import validate_and_sanitize_grounding, extract_factual_numbers_from_ledger
    from arth_rca.reasoning.types import EvidenceLedgerEntry

    temp_ledger = [
        EvidenceLedgerEntry(id=i+1, claim_text=f"Scenario #{s['scenario_id']}", certainty_tier=CertaintyTier.SIMULATION_DEPENDENT, source_entity=f"Scenario#{s['scenario_id']}", metric_value=s['cost_delta'])
        for i, s in enumerate(scenarios_fact_sheet)
    ]
    for s in scenarios_fact_sheet:
        temp_ledger.append(EvidenceLedgerEntry(id=len(temp_ledger)+1, claim_text="Days recovered", certainty_tier=CertaintyTier.SIMULATION_DEPENDENT, source_entity=f"Scenario#{s['scenario_id']}", metric_value=s['days_recovered']))

    v_res = validate_and_sanitize_grounding(
        text=narrative,
        ledger_entries=temp_ledger,
        field_name="pareto_recommendation",
        fallback_deterministic_text=deterministic_fallback,
    )

    return v_res.sanitized_text


def explain_single_scenario(
    scenario_id: int,
    cost_delta: float,
    days_recovered: float,
    project_finish_date: Optional[str],
    critical_path_shift: bool,
    levers_applied: List[Dict[str, Any]],
    llm_client: Optional[GroqClient] = None,
) -> ScenarioExplanationPayload:
    """
    Explains the impact, mechanics, and trade-offs of a single specific what-if scenario.
    """
    client = llm_client or GroqClient()

    facts = {
        "scenario_id": scenario_id,
        "cost_delta": round(cost_delta, 2),
        "days_recovered": round(days_recovered, 2),
        "project_finish_date": project_finish_date,
        "critical_path_shift": critical_path_shift,
        "levers_applied": levers_applied,
    }

    user_prompt = f"""Explain Scenario #{scenario_id} based on these facts:
```json
{json.dumps(facts, indent=2)}
```
"""

    explanation = client.generate(
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=400,
    )

    if "[Grounded Response" in explanation or len(explanation.strip()) < 10:
        shift_desc = "caused a shift in the critical path" if critical_path_shift else "did not shift the critical path"
        explanation = (
            f"[SIMULATION_DEPENDENT] Scenario #{scenario_id} achieves **{days_recovered} days** of project recovery "
            f"at an incremental cost of **${cost_delta:,.2f}**. This intervention {shift_desc} across {len(levers_applied)} lever(s)."
        )

    return ScenarioExplanationPayload(
        scenario_id=scenario_id,
        cost_delta=cost_delta,
        days_recovered=days_recovered,
        project_finish_date=project_finish_date,
        critical_path_shift_description=f"Critical path shift: {'YES' if critical_path_shift else 'NO'}",
        qualitative_tradeoffs=explanation,
        applied_levers=levers_applied,
        certainty_tier=CertaintyTier.SIMULATION_DEPENDENT,
    )
