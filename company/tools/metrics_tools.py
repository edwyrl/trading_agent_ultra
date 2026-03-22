from __future__ import annotations

from contracts.company_contracts import ComputedMetricsDTO


class MetricsTools:
    def compute(self, market_data: dict, financial_data: dict) -> ComputedMetricsDTO:
        _ = (market_data, financial_data)
        return ComputedMetricsDTO(
            technical_metrics={},
            valuation_metrics={},
            financial_quality_metrics={},
            risk_metrics={},
            highlight_flags=[],
        )
