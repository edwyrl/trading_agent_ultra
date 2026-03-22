from __future__ import annotations

from company.analysts.fundamental_analyst import FundamentalAnalyst
from contracts.company_contracts import CompanyContextDTO


class FundamentalAnalystNode:
    def __init__(self, analyst: FundamentalAnalyst):
        self.analyst = analyst

    def __call__(self, state: dict) -> dict:
        context = CompanyContextDTO.model_validate(state["company_context"])
        state["fundamental_output"] = self.analyst.analyze(context)
        return state
