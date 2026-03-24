from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from contracts.enums import MacroBiasTag, MacroThemeType, SourceType

if TYPE_CHECKING:
    from macro.intel.pipeline import MacroIntelPipeline


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
    def __init__(
        self,
        event_loader: Callable[[date], Sequence[dict[str, Any] | MacroEvent]] | None = None,
        intel_pipeline: "MacroIntelPipeline | None" = None,
    ):
        self.event_loader = event_loader
        self.intel_pipeline = intel_pipeline

    def fetch_daily_events(self, as_of_date: date) -> list[MacroEvent]:
        if self.event_loader is None:
            if self.intel_pipeline is None:
                return []
            return self.intel_pipeline.run(as_of_date)

        raw_events = self.event_loader(as_of_date)
        events: list[MacroEvent] = []
        for item in raw_events:
            if isinstance(item, MacroEvent):
                events.append(item)
                continue
            events.append(MacroEvent.model_validate(item))
        return events
