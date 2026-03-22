from __future__ import annotations

from datetime import date

from contracts.macro_contracts import MacroConstraintsSummaryDTO
from contracts.service_ports import MacroSummaryProvider


class MacroConstraintsTool:
    def __init__(self, provider: MacroSummaryProvider):
        self.provider = provider

    def get(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO:
        return self.provider.get_macro_constraints_summary(as_of_date=as_of_date)
