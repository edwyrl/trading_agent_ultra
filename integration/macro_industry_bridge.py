from __future__ import annotations

from contracts.enums import MappingDirection
from contracts.integration_contracts import MacroIndustryConstraintDTO
from contracts.macro_contracts import MacroConstraintsSummaryDTO, MacroIndustryMappingDTO


def derive_macro_constraints_for_industry(
    sw_l1_id: str,
    macro_summary: MacroConstraintsSummaryDTO,
    mappings: list[MacroIndustryMappingDTO],
) -> MacroIndustryConstraintDTO:
    mapping = next((m for m in mappings if m.sw_l1_id == sw_l1_id), None)
    direction = mapping.direction if mapping else MappingDirection.NEUTRAL
    reason = mapping.reason if mapping else "No explicit mapping, default to neutral."

    return MacroIndustryConstraintDTO(
        sw_l1_id=sw_l1_id,
        constraint_direction=direction,
        constraint_reason=reason,
        macro_version_ref=macro_summary.version,
    )
