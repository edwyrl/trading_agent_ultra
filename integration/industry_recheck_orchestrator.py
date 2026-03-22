from __future__ import annotations

from datetime import UTC, datetime

from contracts.enums import MappingDirection, MaterialChangeLevel, UpdateMode
from contracts.integration_contracts import IndustryRecheckDecisionDTO, RecheckQueueItemDTO
from contracts.macro_contracts import MacroDeltaDTO, MacroIndustryMappingDTO
from integration.repository import IntegrationRepository


def decide_industry_recheck(
    macro_delta: MacroDeltaDTO,
    mapping: MacroIndustryMappingDTO,
) -> IndustryRecheckDecisionDTO:
    if not macro_delta.material_change.material_change:
        return IndustryRecheckDecisionDTO(
            sw_l1_id=mapping.sw_l1_id,
            recheck_required=False,
            recommended_mode=None,
            reason_codes=["NO_MACRO_MATERIAL_CHANGE"],
            triggered_by_macro_version=macro_delta.to_version,
        )

    level = macro_delta.material_change.level
    direction = mapping.direction
    reason_codes = [f"MACRO_MATERIAL_{level.value}", f"MAPPING_{direction.value}"]

    # v1 deterministic rule set: prioritize industries with non-neutral macro mapping.
    if direction == MappingDirection.NEUTRAL and level == MaterialChangeLevel.LOW:
        return IndustryRecheckDecisionDTO(
            sw_l1_id=mapping.sw_l1_id,
            recheck_required=False,
            recommended_mode=None,
            reason_codes=reason_codes + ["SKIP_LOW_NEUTRAL"],
            triggered_by_macro_version=macro_delta.to_version,
        )

    if level == MaterialChangeLevel.HIGH and direction != MappingDirection.NEUTRAL:
        mode = UpdateMode.FULL
    elif level == MaterialChangeLevel.NONE:
        return IndustryRecheckDecisionDTO(
            sw_l1_id=mapping.sw_l1_id,
            recheck_required=False,
            recommended_mode=None,
            reason_codes=reason_codes + ["SKIP_NONE_LEVEL"],
            triggered_by_macro_version=macro_delta.to_version,
        )
    elif direction == MappingDirection.NEUTRAL:
        mode = UpdateMode.LIGHT
    else:
        mode = UpdateMode.MARKET

    return IndustryRecheckDecisionDTO(
        sw_l1_id=mapping.sw_l1_id,
        recheck_required=True,
        recommended_mode=mode,
        reason_codes=reason_codes,
        triggered_by_macro_version=macro_delta.to_version,
    )


class IndustryRecheckOrchestrator:
    def __init__(self, repository: IntegrationRepository):
        self.repository = repository

    def build_decisions(
        self,
        macro_delta: MacroDeltaDTO,
        mappings: list[MacroIndustryMappingDTO],
    ) -> list[IndustryRecheckDecisionDTO]:
        # Keep only one mapping per sw_l1_id in case upstream returns duplicates.
        unique: dict[str, MacroIndustryMappingDTO] = {}
        for mapping in mappings:
            unique[mapping.sw_l1_id] = mapping
        return [decide_industry_recheck(macro_delta=macro_delta, mapping=m) for m in unique.values()]

    def enqueue_from_macro(
        self,
        macro_delta: MacroDeltaDTO,
        mappings: list[MacroIndustryMappingDTO],
    ) -> list[RecheckQueueItemDTO]:
        queued_items: list[RecheckQueueItemDTO] = []
        decisions = self.build_decisions(macro_delta=macro_delta, mappings=mappings)
        now = datetime.now(UTC)

        for decision in decisions:
            if not decision.recheck_required or decision.recommended_mode is None:
                continue
            item = RecheckQueueItemDTO(
                queue_id=f"rq:{macro_delta.to_version}:{decision.sw_l1_id}",
                sw_l1_id=decision.sw_l1_id,
                industry_id=decision.sw_l1_id,
                recommended_mode=decision.recommended_mode,
                status="PENDING",
                created_at=now,
            )
            self.repository.enqueue_recheck(
                item=item,
                reason_codes=decision.reason_codes,
                triggered_by_macro_version=decision.triggered_by_macro_version,
            )
            queued_items.append(item)

        return queued_items
