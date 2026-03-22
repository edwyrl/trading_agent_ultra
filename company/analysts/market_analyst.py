from __future__ import annotations

from contracts.company_contracts import CompanyContextDTO


class MarketAnalyst:
    def analyze(self, context: CompanyContextDTO) -> dict:
        return {
            "analyst": "market_analyst",
            "context_version": context.context_version,
            "summary": "v1 placeholder",
        }
