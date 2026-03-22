from __future__ import annotations

from company.analysts.market_analyst import MarketAnalyst
from contracts.company_contracts import CompanyContextDTO


class MarketAnalystNode:
    def __init__(self, analyst: MarketAnalyst):
        self.analyst = analyst

    def __call__(self, state: dict) -> dict:
        context = CompanyContextDTO.model_validate(state["company_context"])
        state["market_output"] = self.analyst.analyze(context)
        return state
