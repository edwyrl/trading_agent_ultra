from __future__ import annotations

from datetime import date

from company.repository import CompanyRepository
from integration.company_context_orchestrator import CompanyContextOrchestrator
from contracts.company_contracts import CompanyContextDTO


class CompanyService:
    def __init__(self, repository: CompanyRepository, orchestrator: CompanyContextOrchestrator | None = None):
        self.repository = repository
        self.orchestrator = orchestrator

    def build_company_context(self, ts_code: str, trade_date: date) -> CompanyContextDTO:
        if self.orchestrator is not None:
            return self.orchestrator.build(ts_code=ts_code, trade_date=trade_date)

        context = self.repository.get_latest_context(ts_code=ts_code, trade_date=trade_date)
        if context is None:
            raise ValueError(f"No company context found for {ts_code} at {trade_date}")
        return context
