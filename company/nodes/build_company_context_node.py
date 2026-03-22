from __future__ import annotations

from datetime import date

from integration.company_context_orchestrator import CompanyContextOrchestrator


class BuildCompanyContextNode:
    def __init__(self, orchestrator: CompanyContextOrchestrator):
        self.orchestrator = orchestrator

    def __call__(self, state: dict) -> dict:
        ts_code = state["ts_code"]
        trade_date = state.get("trade_date", date.today())
        context = self.orchestrator.build(ts_code=ts_code, trade_date=trade_date)
        state["company_context"] = context.model_dump(mode="json")
        return state
