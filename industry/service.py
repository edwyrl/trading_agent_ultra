from __future__ import annotations

from datetime import date

from contracts.enums import SwLevel, UpdateMode
from contracts.industry_contracts import IndustryDeltaDTO, IndustryThesisCardDTO, IndustryThesisSummaryDTO
from industry.prioritizer import IndustryPrioritizer
from industry.repository import IndustryRepository
from industry.retriever import IndustryRetriever
from industry.triggers import IndustryRefreshTrigger
from industry.updater import IndustryUpdater


class IndustryService:
    def __init__(
        self,
        repository: IndustryRepository,
        *,
        retriever: IndustryRetriever | None = None,
        updater: IndustryUpdater | None = None,
        triggers: IndustryRefreshTrigger | None = None,
        prioritizer: IndustryPrioritizer | None = None,
    ):
        self.repository = repository
        self.retriever = retriever or IndustryRetriever()
        self.updater = updater or IndustryUpdater()
        self.triggers = triggers or IndustryRefreshTrigger()
        self.prioritizer = prioritizer or IndustryPrioritizer()

    def _commit_if_available(self) -> None:
        session = getattr(self.repository, "session", None)
        if session is not None and hasattr(session, "commit"):
            session.commit()

    def get_industry_thesis(
        self,
        industry_id: str,
        sw_level: SwLevel,
        *,
        as_of_date: date | None = None,
        auto_refresh: bool = True,
    ) -> IndustryThesisCardDTO | None:
        thesis = self.repository.get_latest(industry_id=industry_id, sw_level=sw_level)
        if thesis is None:
            return None

        if not auto_refresh:
            return thesis

        target_date = as_of_date or date.today()
        modes = self.triggers.resolve_refresh_modes(thesis, as_of_date=target_date)
        if not modes:
            return thesis

        latest = thesis
        for mode in modes:
            refreshed = self.refresh_industry_thesis(
                industry_id=industry_id,
                mode=mode,
                sw_level=sw_level,
                as_of_date=target_date,
            )
            if refreshed is not None:
                latest = refreshed
        return latest

    def refresh_industry_thesis(
        self,
        industry_id: str,
        mode: UpdateMode,
        *,
        sw_level: SwLevel = SwLevel.L1,
        as_of_date: date | None = None,
    ) -> IndustryThesisCardDTO | None:
        current = self.repository.get_latest(industry_id=industry_id, sw_level=sw_level)
        if current is None:
            return None

        target_date = as_of_date or date.today()
        inputs = self.retriever.fetch_incremental_inputs(
            industry_id=industry_id,
            mode=mode,
            as_of_date=target_date,
        )
        updated, delta = self.updater.update(
            current,
            mode=mode,
            incremental_inputs=inputs,
            as_of_date=target_date,
        )
        self.repository.save_snapshot(updated)
        self.repository.save_delta(delta)
        self._commit_if_available()
        return updated

    def get_industry_delta(self, industry_id: str, since_version: str | None = None) -> list[IndustryDeltaDTO]:
        return self.repository.list_deltas(industry_id=industry_id, since_version=since_version)

    def get_industry_thesis_summary(
        self,
        industry_id: str,
        preferred_levels: list[SwLevel] | None = None,
    ) -> IndustryThesisSummaryDTO | None:
        levels = preferred_levels or [SwLevel.L3, SwLevel.L2, SwLevel.L1]
        return self.repository.get_summary(industry_id=industry_id, preferred_levels=levels)

    def get_weekly_refresh_candidates(
        self,
        *,
        limit: int = 8,
        week_key: str | None = None,
        candidate_signals: list[dict] | None = None,
    ) -> list[dict]:
        signals = candidate_signals if candidate_signals is not None else self.retriever.fetch_prioritizer_signals()
        selected = self.prioritizer.select_weekly_candidates(signals, limit=limit)
        target_week_key = week_key or f"{date.today().isocalendar().year}-W{date.today().isocalendar().week:02d}"
        if selected:
            self.repository.save_weekly_candidates(target_week_key, selected)
            self._commit_if_available()
        return selected
