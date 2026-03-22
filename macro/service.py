from __future__ import annotations

from datetime import date

from contracts.macro_contracts import MacroConstraintsSummaryDTO, MacroDeltaDTO, MacroMasterCardDTO
from macro.repository import MacroRepository
from macro.retriever import MacroEvent
from macro.updater import MacroUpdater


class MacroService:
    def __init__(self, repository: MacroRepository, updater: MacroUpdater | None = None):
        self.repository = repository
        self.updater = updater or MacroUpdater(repository=repository)

    def get_macro_master_card(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None:
        return self.repository.get_latest_master(as_of_date)

    def get_macro_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        return self.repository.get_constraints_summary(as_of_date)

    def get_macro_delta(
        self,
        since_version: str | None = None,
        since_date: date | None = None,
    ) -> list[MacroDeltaDTO]:
        return self.repository.list_deltas(since_version=since_version, since_date=since_date)

    def run_daily_incremental_update(
        self,
        as_of_date: date,
        events: list[MacroEvent] | None = None,
    ) -> MacroMasterCardDTO:
        return self.updater.run_daily_incremental_update(as_of_date=as_of_date, events=events)
