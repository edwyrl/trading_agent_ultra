from __future__ import annotations

from contracts.enums import SwLevel, UpdateMode
from contracts.industry_contracts import IndustryDeltaDTO, IndustryThesisCardDTO, IndustryThesisSummaryDTO
from industry.repository import IndustryRepository


class IndustryService:
    def __init__(self, repository: IndustryRepository):
        self.repository = repository

    def get_industry_thesis(
        self,
        industry_id: str,
        sw_level: SwLevel,
        auto_refresh: bool = True,
    ) -> IndustryThesisCardDTO | None:
        # v1 skeleton: auto_refresh orchestration is handled by integration layer.
        return self.repository.get_latest(industry_id=industry_id, sw_level=sw_level)

    def refresh_industry_thesis(self, industry_id: str, mode: UpdateMode) -> None:
        # v1 skeleton: concrete updater logic is intentionally deferred.
        _ = (industry_id, mode)

    def get_industry_delta(self, industry_id: str, since_version: str | None = None) -> list[IndustryDeltaDTO]:
        return self.repository.list_deltas(industry_id=industry_id, since_version=since_version)

    def get_industry_thesis_summary(
        self,
        industry_id: str,
        preferred_levels: list[SwLevel] | None = None,
    ) -> IndustryThesisSummaryDTO | None:
        levels = preferred_levels or [SwLevel.L3, SwLevel.L2, SwLevel.L1]
        return self.repository.get_summary(industry_id=industry_id, preferred_levels=levels)
