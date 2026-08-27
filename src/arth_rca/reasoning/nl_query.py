"""
Deterministic Natural Language Query Engine.
Parses natural language questions into structured analytical intents, executes deterministic
queries against CPM/driver/DCMA data, and synthesizes grounded answers with certainty tiers and citations.
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from sqlmodel import Session

from arth_rca.reasoning.types import (
    QueryIntent,
    NLQueryRequest,
    NLQueryResponse,
    CertaintyTier,
    EvidenceLedgerEntry,
)
from arth_rca.reasoning.evidence_ledger import EvidenceLedger
from arth_rca.reasoning.llm_client import GroqClient
from arth_rca.db.models import Snapshot, Activity, Relationship, Project
from arth_rca.cpm.engine import run_cpm
from arth_rca.cpm.types import CPMActivityInput, CPMRelationshipInput, CPMCalendarInput, CPMOptions
from arth_rca.analytics.driver_detection import detect_negative_float_drivers
from arth_rca.analytics.dcma import run_dcma_14_point_assessment
from arth_rca.analytics.trend import aggregate_historical_trends, SnapshotDataPackage


NL_QUERY_SYSTEM_PROMPT = """You are an AI Project Controls Assistant.
Your objective is to answer the user's schedule analysis question using EXCLUSIVELY the provided Retrieved Facts JSON.

MANDATORY RULES:
1. STRICT GROUNDING: State facts and numbers ONLY as provided in the Retrieved Facts. Do not calculate, estimate, or assume numbers.
2. CITATION & CERTAINTY TIER: Explicitly tag each key finding with its certainty tier:
   - [FACT]: For stated schedule properties (dates, constraints, durations).
   - [INFERENCE]: For CPM metrics (total float days, driving relationships, blast radius counts).
   - [MODELED]: For heuristic classifications or impact scores.
   - [HYPOTHESIS]: For unverified/unresolved root causes.
3. CONCISENESS: Keep the response clear, structured, professional, and directly targeted to the user's question.
"""


def classify_query_intent(query_str: str) -> Tuple[QueryIntent, Dict[str, Any]]:
    """
    Deterministically extracts intent and relevant parameters (e.g. task_code) from query string.
    """
    q_lower = query_str.lower()

    # 1. Activity-specific delay inquiry (e.g. "Why is QTS-28981 delayed?")
    task_code_match = re.search(r'\b([a-zA-Z0-9_\-]+(?:-[a-zA-Z0-9]+)+|[a-zA-Z]+[0-9]{3,})\b', query_str)
    # also match generic codes like ACT_A, DRV_1, T1
    if not task_code_match:
        task_code_match = re.search(r'\b(act_[a-z0-9]+|drv_[a-z0-9]+|t[0-9]+|task_[0-9]+)\b', query_str, re.IGNORECASE)

    extracted_code = task_code_match.group(1).upper() if task_code_match else None

    if extracted_code and any(k in q_lower for k in ["why", "delay", "reason", "cause", "status", "float"]):
        return QueryIntent.DRIVER_WHY_DELAYED, {"task_code": extracted_code}

    # 2. DCMA Health check inquiry
    if any(k in q_lower for k in ["dcma", "health", "missing logic", "negative lag", "constraint check", "quality"]):
        return QueryIntent.DCMA_HEALTH, {}

    # 3. Top drivers inquiry
    if any(k in q_lower for k in ["top driver", "top 3", "top 5", "worst driver", "critical path driver", "delay driver"]):
        return QueryIntent.TOP_DRIVERS, {}

    # 4. Milestone slippage inquiry
    if any(k in q_lower for k in ["milestone", "slip", "finish date", "slippage"]):
        return QueryIntent.MILESTONE_SLIPPAGE, {}

    # 5. Snapshot diff inquiry
    if any(k in q_lower for k in ["diff", "change", "between snapshot", "what changed", "added activity", "removed"]):
        return QueryIntent.SNAPSHOT_DIFF, {}

    # 6. Recovery / optimization inquiry
    if any(k in q_lower for k in ["recover", "optimize", "pareto", "tradeoff", "trade-off", "scenario", "budget", "crash", "fasttrack"]):
        return QueryIntent.RECOVERY_OPTIONS, {}

    return QueryIntent.GENERAL_SCHEDULE, {"task_code": extracted_code}


def execute_nl_query(
    request: NLQueryRequest,
    db: Session,
    llm_client: Optional[GroqClient] = None,
) -> NLQueryResponse:
    """
    Executes a natural language query deterministically against the schedule database
    and synthesizes a grounded answer with certainty tiers and evidence citations.
    """
    client = llm_client or GroqClient()
    ledger = EvidenceLedger()

    # 1. Resolve Target Snapshot
    snap: Optional[Snapshot] = None
    if request.snapshot_id:
        snap = db.query(Snapshot).filter(Snapshot.id == request.snapshot_id).first()
    elif request.project_id:
        snap = (
            db.query(Snapshot)
            .filter(Snapshot.project_id == request.project_id)
            .order_by(Snapshot.data_date.desc())
            .first()
        )
    else:
        snap = db.query(Snapshot).order_by(Snapshot.id.desc()).first()

    if not snap:
        return NLQueryResponse(
            query=request.query,
            intent=QueryIntent.GENERAL_SCHEDULE,
            answer_markdown="[FACT] No schedule snapshot data found in the system.",
            primary_certainty_tier=CertaintyTier.FACT,
            retrieved_facts={},
            citations=[],
        )

    # 2. Extract Intent and Parameters
    intent, params = classify_query_intent(request.query)
    retrieved_facts: Dict[str, Any] = {
        "snapshot_id": snap.id,
        "project_id": snap.project_id,
        "data_date": snap.data_date.strftime("%Y-%m-%d"),
    }
    primary_tier = CertaintyTier.FACT

    # 3. Deterministic Data Retrieval based on Intent
    if intent == QueryIntent.DRIVER_WHY_DELAYED and params.get("task_code"):
        code = params["task_code"]
        act = (
            db.query(Activity)
            .filter(Activity.snapshot_id == snap.id, Activity.task_code == code)
            .first()
        )
        if act:
            retrieved_facts["activity"] = {
                "task_code": act.task_code,
                "name": act.name,
                "total_float": act.total_float,
                "status": act.status,
                "original_duration": act.original_duration,
                "remaining_duration": act.remaining_duration,
                "constraint_type": act.constraint_type,
                "constraint_date": act.constraint_date.strftime("%Y-%m-%d") if act.constraint_date else None,
                "is_driving_path": act.is_driving_path,
            }
            primary_tier = CertaintyTier.INFERENCE
            ledger.record_fact(
                claim_text=f"Activity {act.task_code} has remaining duration of {act.remaining_duration}d and constraint {act.constraint_type or 'None'}",
                source_entity=f"Activity#{act.task_code}",
                metric_name="remaining_duration",
                metric_value=act.remaining_duration,
            )
            ledger.record_inference(
                claim_text=f"Activity {act.task_code} total float is {act.total_float} days",
                source_entity=f"Activity#{act.task_code}",
                metric_name="total_float",
                metric_value=act.total_float,
            )
        else:
            retrieved_facts["activity_not_found"] = code

    elif intent == QueryIntent.DCMA_HEALTH:
        # Pull activities & relationships to compute exact DCMA assessment
        tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
        rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()

        acts_input = {
            t.id: CPMActivityInput(
                task_id=t.id,
                task_code=t.task_code,
                calendar_id=t.calendar_id or 1,
                original_duration_days=t.original_duration,
                remaining_duration_days=t.remaining_duration,
                status=t.status,
                cstr_type=t.constraint_type,
                cstr_date=t.constraint_date,
                is_milestone=t.is_milestone,
            )
            for t in tasks
        }
        rels_input = [
            CPMRelationshipInput(
                rel_id=r.id or idx,
                pred_task_id=r.predecessor_activity_id,
                succ_task_id=r.successor_activity_id,
                rel_type=r.relationship_type or "FS",
                lag_days=r.lag,
            )
            for idx, r in enumerate(rels, start=1)
        ]
        cals_input = {
            1: CPMCalendarInput(
                clndr_id=1,
                name="Standard 5-Day",
                working_days=[True, True, True, True, True, False, False],
                work_hours_per_day=8.0,
                holidays=[],
                work_exceptions={},
            )
        }
        cpm_res = run_cpm(acts_input, rels_input, cals_input, CPMOptions(data_date=snap.data_date))

        class TaskWrapper:
            def __init__(self, act: CPMActivityInput):
                self.task_id = act.task_id
                self.task_code = act.task_code
                self.status_code = "TK_Complete" if act.status == "COMPLETED" else ("TK_Active" if act.status == "IN_PROGRESS" else "TK_NotStart")
                self.task_type = "TT_FinMile" if act.is_milestone else "TT_Task"
                self.cstr_type = act.cstr_type
                self.cstr_date = act.cstr_date
                self.target_durn_hr_cnt = act.original_duration_days * 8.0
                self.act_start_date = act.act_start_date
                self.act_end_date = act.act_finish_date

        raw_tasks_dict = {tid: TaskWrapper(act) for tid, act in acts_input.items()}
        dcma_res = run_dcma_14_point_assessment(
            cpm_result=cpm_res,
            raw_tasks=raw_tasks_dict,
            raw_relationships=rels_input,
            data_date=snap.data_date,
            snapshot_id=snap.id,
        )

        retrieved_facts["dcma_overall_health_score"] = dcma_res.overall_health_score
        retrieved_facts["dcma_failed_checks_count"] = len([m for m in dcma_res.metrics if not m.passed])
        retrieved_facts["dcma_metrics"] = [
            {
                "check_number": m.check_number,
                "name": m.name,
                "actual_value": round(m.actual_value, 2) if isinstance(m.actual_value, float) else m.actual_value,
                "target_threshold": m.target_threshold,
                "passed": m.passed,
                "failing_count": m.failing_activity_count,
            }
            for m in dcma_res.metrics
        ]
        primary_tier = CertaintyTier.FACT
        ledger.record_fact(
            claim_text=f"Overall DCMA Health Score is {dcma_res.overall_health_score}%",
            source_entity=f"DCMA#{snap.id}",
            metric_name="overall_health_score",
            metric_value=dcma_res.overall_health_score,
        )

    elif intent == QueryIntent.TOP_DRIVERS:
        tasks = db.query(Activity).filter(Activity.snapshot_id == snap.id).all()
        rels = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).all()

        acts_input = {
            t.id: CPMActivityInput(
                task_id=t.id,
                task_code=t.task_code,
                calendar_id=t.calendar_id or 1,
                original_duration_days=t.original_duration,
                remaining_duration_days=t.remaining_duration,
                status=t.status,
                cstr_type=t.constraint_type,
                cstr_date=t.constraint_date,
                is_milestone=t.is_milestone,
            )
            for t in tasks
        }
        rels_input = [
            CPMRelationshipInput(
                rel_id=r.id or idx,
                pred_task_id=r.predecessor_activity_id,
                succ_task_id=r.successor_activity_id,
                rel_type=r.relationship_type or "FS",
                lag_days=r.lag,
            )
            for idx, r in enumerate(rels, start=1)
        ]
        cals_input = {
            1: CPMCalendarInput(
                clndr_id=1,
                name="Standard 5-Day",
                working_days=[True, True, True, True, True, False, False],
                work_hours_per_day=8.0,
                holidays=[],
                work_exceptions={},
            )
        }
        cpm_res = run_cpm(acts_input, rels_input, cals_input, CPMOptions(data_date=snap.data_date))
        driver_res = detect_negative_float_drivers(cpm_res, acts_input, rels_input, snapshot_id=snap.id)

        retrieved_facts["total_negative_float_tasks"] = driver_res.total_negative_float_activities
        retrieved_facts["driver_head_count"] = driver_res.driver_head_count
        retrieved_facts["top_drivers"] = [
            {
                "task_code": d.driver_task_code,
                "name": getattr(d, "driver_name", None) or d.driver_task_code,
                "total_float_days": round(d.driver_total_float_days, 1),
                "blast_radius_impacted_count": getattr(d, "downstream_activity_count", len(getattr(d, "blast_radius_nodes", []))),
                "root_cause_type": d.root_cause_type,
                "root_cause_summary": getattr(d, "root_cause_description", getattr(d, "root_cause_summary", "")),
            }
            for d in driver_res.drivers[:5]
        ]
        primary_tier = CertaintyTier.INFERENCE
        for d in driver_res.drivers[:3]:
            chain_len = getattr(d, "downstream_activity_count", len(getattr(d, "blast_radius_nodes", [])))
            ledger.record_inference(
                claim_text=f"Driver {d.driver_task_code} has {round(d.driver_total_float_days, 1)}d float impacting {chain_len} activities",
                source_entity=f"Activity#{d.driver_task_code}",
                metric_name="total_float_days",
                metric_value=round(d.driver_total_float_days, 1),
            )

    elif intent == QueryIntent.MILESTONE_SLIPPAGE:
        milestones = (
            db.query(Activity)
            .filter(Activity.snapshot_id == snap.id, Activity.is_milestone == True)
            .all()
        )
        retrieved_facts["milestones"] = [
            {
                "task_code": m.task_code,
                "name": m.name,
                "early_finish": m.early_finish.strftime("%Y-%m-%d") if m.early_finish else None,
                "total_float": m.total_float,
                "status": m.status,
            }
            for m in milestones[:10]
        ]
        primary_tier = CertaintyTier.FACT
        if milestones:
            worst = min(milestones, key=lambda m: m.total_float or 0.0)
            ledger.record_inference(
                claim_text=f"Worst milestone float: {worst.task_code} ({worst.name}) with {worst.total_float}d float",
                source_entity=f"Activity#{worst.task_code}",
                metric_name="total_float",
                metric_value=worst.total_float,
            )

    else:
        # General overview
        act_count = db.query(Activity).filter(Activity.snapshot_id == snap.id).count()
        rel_count = db.query(Relationship).filter(Relationship.snapshot_id == snap.id).count()
        retrieved_facts["total_activities"] = act_count
        retrieved_facts["total_relationships"] = rel_count
        primary_tier = CertaintyTier.FACT
        ledger.record_fact(
            claim_text=f"Snapshot contains {act_count} activities and {rel_count} relationships",
            source_entity=f"Snapshot#{snap.id}",
            metric_name="activity_count",
            metric_value=act_count,
        )

    # 4. Synthesize Grounded Answer via Groq
    user_prompt = f"""Question: {request.query}

Retrieved Facts JSON:
```json
{json.dumps(retrieved_facts, indent=2)}
```

Provide a concise, direct, professional response answering the question strictly using the Retrieved Facts."""

    synthesized_markdown = client.generate(
        system_prompt=NL_QUERY_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=600,
    )

    # Ensure offline fallback is formatted cleanly with certainty tier
    if "[Grounded Response" in synthesized_markdown or len(synthesized_markdown.strip()) < 10:
        if intent == QueryIntent.DRIVER_WHY_DELAYED and "activity" in retrieved_facts:
            act_info = retrieved_facts["activity"]
            synthesized_markdown = (
                f"[{primary_tier.value}] Activity **{act_info['task_code']}** ({act_info['name']}) has "
                f"**{act_info['total_float']} days** of total float. "
                f"Remaining duration is **{act_info['remaining_duration']} days** (Status: {act_info['status']}). "
                f"Constraint applied: {act_info['constraint_type'] or 'None'}."
            )
        elif intent == QueryIntent.DCMA_HEALTH:
            synthesized_markdown = (
                f"[{primary_tier.value}] The project DCMA Schedule Health Score is **{retrieved_facts.get('dcma_overall_health_score')}%**. "
                f"Out of 14 standard metrics, **{retrieved_facts.get('dcma_failed_checks_count')}** check(s) flagged compliance anomalies."
            )
        elif intent == QueryIntent.TOP_DRIVERS:
            drivers = retrieved_facts.get("top_drivers", [])
            drv_lines = "\n".join([f"- [{primary_tier.value}] **{d['task_code']}** ({d['name']}): {d['total_float_days']}d float, blast radius {d['blast_radius_impacted_count']} tasks." for d in drivers])
            synthesized_markdown = (
                f"[{primary_tier.value}] Identified **{retrieved_facts.get('driver_head_count')}** driver heads affecting "
                f"**{retrieved_facts.get('total_negative_float_tasks')}** negative float tasks.\n\n{drv_lines}"
            )
        else:
            synthesized_markdown = f"[{primary_tier.value}] Schedule analysis for snapshot {snap.id} (Data Date: {snap.data_date.strftime('%Y-%m-%d')})."

    return NLQueryResponse(
        query=request.query,
        intent=intent,
        answer_markdown=synthesized_markdown,
        primary_certainty_tier=primary_tier,
        retrieved_facts=retrieved_facts,
        citations=ledger.get_entries(),
    )
