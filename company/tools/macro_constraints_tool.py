from __future__ import annotations

from datetime import date

from contracts.company_contracts import IndustryMappingSignalForCompanyDTO
from contracts.enums import MappingDirection
from contracts.macro_contracts import MacroConstraintsSummaryDTO
from contracts.service_ports import MacroSummaryProvider


class MacroConstraintsTool:
    def __init__(self, provider: MacroSummaryProvider):
        self.provider = provider

    def get(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        return self.provider.get_macro_constraints_summary(as_of_date=as_of_date)

    def get_mapping_signal(
        self,
        sw_l1_id: str,
        version: str | None = None,
    ) -> IndustryMappingSignalForCompanyDTO:
        mappings = self.provider.get_macro_industry_mappings(version=version)
        mapping = next((m for m in mappings if m.sw_l1_id == sw_l1_id), None)
        if mapping is None:
            return IndustryMappingSignalForCompanyDTO(
                sw_l1_id=sw_l1_id,
                direction=MappingDirection.NEUTRAL,
                reason="No explicit macro mapping; fallback to neutral.",
            )
        return IndustryMappingSignalForCompanyDTO(
            sw_l1_id=sw_l1_id,
            direction=mapping.direction,
            reason=mapping.reason,
        )
