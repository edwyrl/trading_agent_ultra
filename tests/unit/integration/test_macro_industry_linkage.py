from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.confidence import ConfidenceDTO
from contracts.enums import (
    ConfidenceLevel,
    EntityType,
    MacroBiasTag,
    MappingDirection,
    MaterialChangeLevel,
    SourceType,
    UpdateMode,
)
from contracts.integration_contracts import RecheckQueueItemDTO
from contracts.macro_contracts import (
    MacroConstraintsSummaryDTO,
    MacroDeltaDTO,
    MacroIndustryMappingDTO,
)
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO
from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator, decide_industry_recheck
from integration.macro_industry_bridge import derive_macro_constraints_for_industry, derive_macro_constraints_map


class InMemoryIntegrationRepository:
    def __init__(self) -> None:
        self.items: dict[str, RecheckQueueItemDTO] = {}

    def enqueue_recheck(self, item: RecheckQueueItemDTO, reason_codes: list[str], triggered_by_macro_version: str) -> None:
        _ = (reason_codes, triggered_by_macro_version)
        self.items[item.queue_id] = item

    def list_pending_rechecks(self) -> list[RecheckQueueItemDTO]:
        return [item for item in self.items.values() if item.status == "PENDING"]


def _macro_delta(material: bool, level: MaterialChangeLevel) -> MacroDeltaDTO:
    return MacroDeltaDTO(
        delta_id="macro-delta:test",
        entity_type=EntityType.MACRO_MASTER,
        entity_id="macro_master",
        from_version="v0",
        to_version="v1",
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


def test_decide_recheck_high_positive_full() -> None:
    decision = decide_industry_recheck(
        macro_delta=_macro_delta(material=True, level=MaterialChangeLevel.HIGH),
        mapping=MacroIndustryMappingDTO(
            sw_l1_id="801010",
            sw_l1_name="农林牧渔",
            direction=MappingDirection.POSITIVE,
            score=0.7,
            reason="test",
        ),
    )
    assert decision.recheck_required is True
    assert decision.recommended_mode == UpdateMode.FULL


def test_decide_recheck_low_neutral_skip() -> None:
    decision = decide_industry_recheck(
        macro_delta=_macro_delta(material=True, level=MaterialChangeLevel.LOW),
        mapping=MacroIndustryMappingDTO(
            sw_l1_id="801020",
            sw_l1_name="采掘",
            direction=MappingDirection.NEUTRAL,
            score=0.0,
            reason="test",
        ),
    )
    assert decision.recheck_required is False
    assert decision.recommended_mode is None


def test_orchestrator_enqueues_only_required_items() -> None:
    repo = InMemoryIntegrationRepository()
    orchestrator = IndustryRecheckOrchestrator(repository=repo)
    mappings = [
        MacroIndustryMappingDTO(
            sw_l1_id="801010",
            sw_l1_name="农林牧渔",
            direction=MappingDirection.NEGATIVE,
            score=-0.6,
            reason="test-1",
        ),
        MacroIndustryMappingDTO(
            sw_l1_id="801020",
            sw_l1_name="采掘",
            direction=MappingDirection.NEUTRAL,
            score=0.0,
            reason="test-2",
        ),
    ]
    queued = orchestrator.enqueue_from_macro(
        macro_delta=_macro_delta(material=True, level=MaterialChangeLevel.MEDIUM),
        mappings=mappings,
    )
    assert len(queued) == 2
    assert all(item.recommended_mode in {UpdateMode.MARKET, UpdateMode.LIGHT} for item in queued)


def test_macro_industry_bridge_default_neutral() -> None:
    summary = MacroConstraintsSummaryDTO(
        version="macro-v1",
        as_of_date=date(2026, 3, 22),
        current_macro_bias=[MacroBiasTag.POLICY_EXPECTATION_DOMINANT],
        macro_mainline="政策预期偏强",
        style_impact="成长风格活跃",
        material_change=MaterialChangeDTO(
            material_change=False,
            level=MaterialChangeLevel.NONE,
            reasons=[],
        ),
        confidence=ConfidenceDTO(score=0.6, level=ConfidenceLevel.MEDIUM),
    )
    mappings = [
        MacroIndustryMappingDTO(
            sw_l1_id="801010",
            sw_l1_name="农林牧渔",
            direction=MappingDirection.POSITIVE,
            score=0.3,
            reason="test",
        )
    ]
    constraint = derive_macro_constraints_for_industry("801020", summary, mappings)
    assert constraint.constraint_direction == MappingDirection.NEUTRAL

    constraint_map = derive_macro_constraints_map(["801010", "801020"], summary, mappings)
    assert set(constraint_map.keys()) == {"801010", "801020"}
