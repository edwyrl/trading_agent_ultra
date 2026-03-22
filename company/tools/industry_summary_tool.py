from __future__ import annotations

from contracts.enums import SwLevel
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.service_ports import IndustrySummaryProvider


class IndustrySummaryTool:
    def __init__(self, provider: IndustrySummaryProvider):
        self.provider = provider

    def get(
        self,
        industry_id: str,
        preferred_levels: list[SwLevel] | None = None,
    ) -> IndustryThesisSummaryDTO:
        return self.provider.get_industry_thesis_summary(
            industry_id=industry_id,
            preferred_levels=preferred_levels,
        )
