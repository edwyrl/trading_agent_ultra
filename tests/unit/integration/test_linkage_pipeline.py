from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.confidence import ConfidenceDTO
from contracts.enums import (
    ConfidenceLevel,
    EntityType,
    MappingDirection,
    MaterialChangeLevel,
    SourceType,
    UpdateMode,
)
from contracts.integration_contracts import RecheckQueueItemDTO
from contracts.macro_contracts import MacroDeltaDTO, MacroIndustryMappingDTO
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO
from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator
from integration.linkage_service import MacroIndustryLinkageService
from integration.recheck_executor import IndustryRecheckExecutor


class InMemoryIntegrationRepository:
    def __init__(self) -> None:
        self.items: dict[str, RecheckQueueItemDTO] = {}

    def enqueue_recheck(self, item: RecheckQueueItemDTO, reason_codes: list[str], triggered_by_macro_version: str) -> None:
        item.reason_codes = reason_codes
        item.triggered_by_macro_version = triggered_by_macro_version
        self.items[item.queue_id] = item

    def list_pending_rechecks(self) -> list[RecheckQueueItemDTO]:
        return [item for item in self.items.values() if item.status == "PENDING"]

    def update_recheck_status(self, queue_id: str, status: str, note: str | None = None) -> None:
        _ = note
        if queue_id in self.items:
            self.items[queue_id].status = status


class StubMacroService:
    def __init__(self, deltas: list[MacroDeltaDTO], mappings_by_version: dict[str, list[MacroIndustryMappingDTO]]):
        self._deltas = deltas
        self._mappings_by_version = mappings_by_version

    def get_macro_delta(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]:
        _ = (since_version, since_date)
        return self._deltas

    def get_macro_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]:
        if version is None:
            # latest fallback
            return next(iter(self._mappings_by_version.values()), [])
        return self._mappings_by_version.get(version, [])


class StubIndustryService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UpdateMode]] = []

    def refresh_industry_thesis(self, industry_id: str, mode: UpdateMode) -> None:
        self.calls.append((industry_id, mode))


def _delta(material: bool, level: MaterialChangeLevel, to_version: str) -> MacroDeltaDTO:
    return MacroDeltaDTO(
        delta_id=f"macro-delta:{to_version}",
        entity_type=EntityType.MACRO_MASTER,
        entity_id="macro_master",
        from_version="v0",
        to_version=to_version,
        as_of_date=date(2026, 3, 22),
        changed_fields=["current_macro_bias"],
        summary="test",
        reasons=["test"],
        impact_scope=["industry"],
        material_change=MaterialChangeDTO(material_change=material, level=level, reasons=["test"]),
        source_refs=[
            SourceRefDTO(
                source_type=SourceType.INTERNAL_SUMMARY,
                title="test-source",
                retrieved_at=datetime.now(UTC),
            )
        ],
        created_at=datetime.now(UTC),
    )


def test_linkage_enqueue_from_recent_deltas() -> None:
    repo = InMemoryIntegrationRepository()
    orchestrator = IndustryRecheckOrchestrator(repository=repo)
    macro = StubMacroService(
        deltas=[_delta(material=True, level=MaterialChangeLevel.MEDIUM, to_version="macro-v1")],
        mappings_by_version={
            "macro-v1": [
                MacroIndustryMappingDTO(
                    sw_l1_id="801010",
                    sw_l1_name="农林牧渔",
                    direction=MappingDirection.POSITIVE,
                    score=0.5,
                    reason="test",
                )
            ]
        },
    )

    linkage = MacroIndustryLinkageService(macro_service=macro, orchestrator=orchestrator)
    queued = linkage.enqueue_from_recent_deltas()

    assert len(queued) == 1
    assert queued[0].queue_id.startswith("rq:macro-v1:")
    assert repo.list_pending_rechecks()[0].recommended_mode == UpdateMode.MARKET


def test_recheck_executor_marks_done() -> None:
    repo = InMemoryIntegrationRepository()
    item = RecheckQueueItemDTO(
        queue_id="rq:test:801010",
        sw_l1_id="801010",
        industry_id="801010",
        recommended_mode=UpdateMode.MARKET,
        status="PENDING",
        created_at=datetime.now(UTC),
    )
    repo.items[item.queue_id] = item

    industry_service = StubIndustryService()
    executor = IndustryRecheckExecutor(repository=repo, industry_service=industry_service)

    stats = executor.run_pending()

    assert stats == {"total": 1, "done": 1, "failed": 0}
    assert industry_service.calls == [("801010", UpdateMode.MARKET)]
    assert repo.items[item.queue_id].status == "DONE"
