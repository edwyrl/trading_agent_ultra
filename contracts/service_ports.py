from __future__ import annotations

from datetime import date
from typing import Protocol

from contracts.company_contracts import CompanyContextDTO
from contracts.enums import SwLevel
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.macro_contracts import MacroConstraintsSummaryDTO, MacroIndustryMappingDTO


class MacroSummaryProvider(Protocol):
    def get_macro_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None: ...

    def get_macro_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]: ...


class IndustrySummaryProvider(Protocol):
    def get_industry_thesis_summary(
        self,
        industry_id: str,
        preferred_levels: list[SwLevel] | None = None,
    ) -> IndustryThesisSummaryDTO | None: ...


class CompanyContextBuilder(Protocol):
    def build_company_context(self, ts_code: str, trade_date: date) -> CompanyContextDTO: ...
