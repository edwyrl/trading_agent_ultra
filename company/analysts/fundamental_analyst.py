from __future__ import annotations

from contracts.company_contracts import CompanyContextDTO


class FundamentalAnalyst:
    def analyze(self, context: CompanyContextDTO) -> dict:
        return {
            "analyst": "fundamental_analyst",
            "context_version": context.context_version,
            "summary": "v1 placeholder",
        }
