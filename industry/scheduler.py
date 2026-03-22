from __future__ import annotations

from datetime import date

from contracts.enums import SwLevel, UpdateMode
from industry.service import IndustryService


class IndustryScheduler:
    def __init__(self, service: IndustryService):
        self.service = service

    def run_weekly_full_refresh(
        self,
        *,
        as_of_date: date | None = None,
        limit: int = 8,
    ) -> dict:
        target_date = as_of_date or date.today()
        candidates = self.service.get_weekly_refresh_candidates(limit=limit)

        refreshed = 0
        for candidate in candidates:
            if not candidate.get("selected", False):
                continue
            industry_id = candidate["industry_id"]
            level_str = candidate.get("sw_level", SwLevel.L1.value)
            level = SwLevel(level_str)
            result = self.service.refresh_industry_thesis(
                industry_id=industry_id,
                mode=UpdateMode.FULL,
                sw_level=level,
                as_of_date=target_date,
            )
            if result is not None:
                refreshed += 1

        return {
            "as_of_date": target_date.isoformat(),
            "candidate_count": len(candidates),
            "refreshed_count": refreshed,
        }
