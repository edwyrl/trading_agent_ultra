from __future__ import annotations

from datetime import date


class CompanyDataService:
    def fetch_company_bundle(self, ts_code: str, trade_date: date) -> dict:
        """Fetch deterministic company, market, and financial data bundle."""
        _ = (ts_code, trade_date)
        return {}
