from __future__ import annotations

from datetime import date

from contracts.company_contracts import CompanyContextDTO
from contracts.service_ports import CompanyContextBuilder


class CompanyContextOrchestrator:
    def __init__(self, builder: CompanyContextBuilder):
        self.builder = builder

    def build(self, ts_code: str, trade_date: date) -> CompanyContextDTO:
        return self.builder.build_company_context(ts_code=ts_code, trade_date=trade_date)
