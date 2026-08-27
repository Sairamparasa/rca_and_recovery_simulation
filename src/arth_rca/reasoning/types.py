"""
Data types and schemas for the AI Reasoning Layer.
Enforces certainty-tier propagation, evidence ledger citations, and structured query payloads.
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field


class CertaintyTier(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    MODELED = "MODELED"
    SIMULATION_DEPENDENT = "SIMULATION_DEPENDENT"
    HYPOTHESIS = "HYPOTHESIS"


class EvidenceLedgerEntry(BaseModel):
    id: Optional[int] = None
    claim_text: str
    certainty_tier: CertaintyTier
    source_entity: str  # e.g., "Snapshot#1", "Activity#QTS-28981", "DCMA#Check1", "Scenario#2"
    metric_name: Optional[str] = None
    metric_value: Optional[Union[float, int, str, bool]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NarrativeReportPayload(BaseModel):
    snapshot_id: int
    data_date: datetime
    project_name: str
    executive_summary: str
    dcma_health_narrative: str
    critical_path_and_drivers_narrative: str
    snapshot_trends_narrative: Optional[str] = None
    evidence_ledger: List[EvidenceLedgerEntry] = Field(default_factory=list)
    unresolved_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)


class QueryIntent(str, Enum):
    DRIVER_WHY_DELAYED = "DRIVER_WHY_DELAYED"
    TOP_DRIVERS = "TOP_DRIVERS"
    DCMA_HEALTH = "DCMA_HEALTH"
    MILESTONE_SLIPPAGE = "MILESTONE_SLIPPAGE"
    SNAPSHOT_DIFF = "SNAPSHOT_DIFF"
    RECOVERY_OPTIONS = "RECOVERY_OPTIONS"
    GENERAL_SCHEDULE = "GENERAL_SCHEDULE"


class NLQueryRequest(BaseModel):
    query: str
    snapshot_id: Optional[int] = None
    project_id: Optional[int] = None


class NLQueryResponse(BaseModel):
    query: str
    intent: QueryIntent
    answer_markdown: str
    primary_certainty_tier: CertaintyTier
    retrieved_facts: Dict[str, Any] = Field(default_factory=dict)
    citations: List[EvidenceLedgerEntry] = Field(default_factory=list)


class ScenarioExplanationPayload(BaseModel):
    scenario_id: int
    cost_delta: float
    days_recovered: float
    project_finish_date: Optional[str] = None
    critical_path_shift_description: str
    qualitative_tradeoffs: str
    applied_levers: List[Dict[str, Any]] = Field(default_factory=list)
    certainty_tier: CertaintyTier = CertaintyTier.SIMULATION_DEPENDENT
