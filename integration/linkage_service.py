from __future__ import annotations

from datetime import date

from contracts.integration_contracts import RecheckQueueItemDTO
from contracts.macro_contracts import MacroDeltaDTO
from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator
from macro.service import MacroService


class MacroIndustryLinkageService:
    """Build recheck queue items from macro deltas and macro->industry mappings."""

    def __init__(self, macro_service: MacroService, orchestrator: IndustryRecheckOrchestrator):
        self.macro_service = macro_service
        self.orchestrator = orchestrator

    def enqueue_from_delta(self, macro_delta: MacroDeltaDTO) -> list[RecheckQueueItemDTO]:
        mappings = self.macro_service.get_macro_industry_mappings(version=macro_delta.to_version)
        if not mappings:
            # Fallback to latest mappings so linkage can still run when version-specific snapshots are absent.
            mappings = self.macro_service.get_macro_industry_mappings(version=None)
        if not mappings:
            return []
        return self.orchestrator.enqueue_from_macro(macro_delta=macro_delta, mappings=mappings)

    def enqueue_from_recent_deltas(
        self,
        since_version: str | None = None,
        since_date: date | None = None,
    ) -> list[RecheckQueueItemDTO]:
        deltas = self.macro_service.get_macro_delta(since_version=since_version, since_date=since_date)
        queued: list[RecheckQueueItemDTO] = []
        # Process oldest first for deterministic queue order.
        for delta in sorted(deltas, key=lambda d: (d.as_of_date, d.created_at)):
            queued.extend(self.enqueue_from_delta(delta))
        return queued
