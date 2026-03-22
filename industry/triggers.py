from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from contracts.enums import UpdateMode
from contracts.industry_contracts import IndustryThesisCardDTO

class IndustryRefreshTrigger:
    def __init__(self, now_provider: Callable[[], datetime] | None = None):
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def should_light_update(
        self,
        last_news_update_at: datetime | None,
        *,
        threshold_hours: int = 24,
        now: datetime | None = None,
    ) -> bool:
        if last_news_update_at is None:
            return True
        current = now or self._now_provider()
        return (current - last_news_update_at) >= timedelta(hours=threshold_hours)

    def should_market_update(
        self,
        last_market_data_update_at: datetime | None,
        *,
        as_of_date: date,
    ) -> bool:
        if last_market_data_update_at is None:
            return True
        return last_market_data_update_at.date() < as_of_date

    def should_full_refresh(
        self,
        last_full_refresh_at: datetime | None,
        *,
        as_of_date: date,
        interval_days: int = 7,
    ) -> bool:
        if last_full_refresh_at is None:
            return True
        return (as_of_date - last_full_refresh_at.date()).days >= interval_days

    def resolve_refresh_modes(
        self,
        thesis: IndustryThesisCardDTO,
        *,
        as_of_date: date,
    ) -> list[UpdateMode]:
        if self.should_full_refresh(thesis.last_full_refresh_at, as_of_date=as_of_date):
            return [UpdateMode.FULL]

        modes: list[UpdateMode] = []
        if self.should_market_update(thesis.last_market_data_update_at, as_of_date=as_of_date):
            modes.append(UpdateMode.MARKET)
        if self.should_light_update(thesis.last_news_update_at):
            modes.append(UpdateMode.LIGHT)
        return modes
