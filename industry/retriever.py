from __future__ import annotations

from datetime import date

from contracts.enums import UpdateMode

class IndustryRetriever:
    def fetch_incremental_inputs(
        self,
        industry_id: str,
        *,
        mode: UpdateMode,
        as_of_date: date,
    ) -> dict:
        return {
            "industry_id": industry_id,
            "mode": mode.value,
            "as_of_date": as_of_date.isoformat(),
            "summary": f"{mode.value} refresh inputs collected",
        }

    def fetch_prioritizer_signals(self) -> list[dict]:
        return []
