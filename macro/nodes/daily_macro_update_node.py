from __future__ import annotations

from datetime import date

from macro.retriever import MacroEvent
from macro.service import MacroService

class DailyMacroUpdateNode:
    def __init__(self, service: MacroService):
        self.service = service

    def __call__(self, state: dict) -> dict:
        as_of_date = state.get("as_of_date", date.today())
        if isinstance(as_of_date, str):
            as_of_date = date.fromisoformat(as_of_date)
        events = state.get("macro_events")
        parsed_events = [MacroEvent.model_validate(item) for item in events] if events else None
        master = self.service.run_daily_incremental_update(as_of_date=as_of_date, events=parsed_events)
        state["macro_master"] = master.model_dump(mode="json")
        return state
