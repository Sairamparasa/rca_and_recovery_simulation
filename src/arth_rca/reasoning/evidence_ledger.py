"""
Evidence Ledger tracker linking narrative assertions to verifiable database facts and certainty tiers.
"""

from typing import List, Optional, Any, Union
from arth_rca.reasoning.types import EvidenceLedgerEntry, CertaintyTier


class EvidenceLedger:
    def __init__(self):
        self.entries: List[EvidenceLedgerEntry] = []

    def record_fact(
        self,
        claim_text: str,
        source_entity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[Union[float, int, str, bool]] = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            id=len(self.entries) + 1,
            claim_text=claim_text,
            certainty_tier=CertaintyTier.FACT,
            source_entity=source_entity,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        self.entries.append(entry)
        return entry

    def record_inference(
        self,
        claim_text: str,
        source_entity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[Union[float, int, str, bool]] = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            id=len(self.entries) + 1,
            claim_text=claim_text,
            certainty_tier=CertaintyTier.INFERENCE,
            source_entity=source_entity,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        self.entries.append(entry)
        return entry

    def record_modeled(
        self,
        claim_text: str,
        source_entity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[Union[float, int, str, bool]] = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            id=len(self.entries) + 1,
            claim_text=claim_text,
            certainty_tier=CertaintyTier.MODELED,
            source_entity=source_entity,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        self.entries.append(entry)
        return entry

    def record_simulation(
        self,
        claim_text: str,
        source_entity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[Union[float, int, str, bool]] = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            id=len(self.entries) + 1,
            claim_text=claim_text,
            certainty_tier=CertaintyTier.SIMULATION_DEPENDENT,
            source_entity=source_entity,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        self.entries.append(entry)
        return entry

    def record_hypothesis(
        self,
        claim_text: str,
        source_entity: str,
        metric_name: Optional[str] = None,
        metric_value: Optional[Union[float, int, str, bool]] = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            id=len(self.entries) + 1,
            claim_text=claim_text,
            certainty_tier=CertaintyTier.HYPOTHESIS,
            source_entity=source_entity,
            metric_name=metric_name,
            metric_value=metric_value,
        )
        self.entries.append(entry)
        return entry

    def get_entries(self) -> List[EvidenceLedgerEntry]:
        return list(self.entries)
