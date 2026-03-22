from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from contracts.enums import MacroBiasTag, MacroThemeType, SourceType


class MacroEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    title: str
    summary: str = ""
    theme_type: MacroThemeType

    source_type: SourceType = SourceType.NEWS
    published_at: datetime | None = None
    url: str | None = None
    source_id: str | None = None
    provider: str | None = None
    bias_hint: MacroBiasTag | None = None


class MacroRetriever:
    def __init__(self, event_loader: Callable[[date], Sequence[dict[str, Any] | MacroEvent]] | None = None):
        self.event_loader = event_loader

    def fetch_daily_events(self, as_of_date: date) -> list[MacroEvent]:
        if self.event_loader is None:
            return []

        raw_events = self.event_loader(as_of_date)
        events: list[MacroEvent] = []
        for item in raw_events:
            if isinstance(item, MacroEvent):
                events.append(item)
                continue
            events.append(MacroEvent.model_validate(item))
        return events
