from __future__ import annotations

from datetime import date

from company.repository import CompanyRepository
from contracts.company_contracts import CompanyContextDTO


class CompanyService:
    def __init__(self, repository: CompanyRepository):
        self.repository = repository

    def build_company_context(self, ts_code: str, trade_date: date) -> CompanyContextDTO:
        # v1 skeleton: orchestration happens in integration/company_context_orchestrator.py
        context = self.repository.get_latest_context(ts_code=ts_code, trade_date=trade_date)
        if context is None:
            raise ValueError(f"No company context found for {ts_code} at {trade_date}")
        return context
