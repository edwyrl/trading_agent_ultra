from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.enums import SwLevel


class CompanyDataService:
    def fetch_company_bundle(self, ts_code: str, trade_date: date) -> dict:
        """Fetch deterministic company, market, and financial data bundle."""
        now = datetime.now(UTC)
        return {
            "ts_code": ts_code,
            "company_name": ts_code,
            "trade_date": trade_date,
            "sw_l1_id": "801010",
            "sw_l1_name": "农林牧渔",
            "sw_l2_id": None,
            "sw_l2_name": None,
            "sw_l3_id": None,
            "sw_l3_name": None,
            "primary_industry_level": SwLevel.L1,
            "market_data": {},
            "financial_data": {},
            "news_texts": [],
            "market_data_ref": {"ref_id": f"market:{ts_code}:{trade_date:%Y%m%d}", "as_of_date": trade_date, "updated_at": now},
            "financial_data_ref": {
                "ref_id": f"financial:{ts_code}:{trade_date:%Y%m%d}",
                "as_of_date": trade_date,
                "updated_at": now,
            },
            "news_data_ref": {"ref_id": f"news:{ts_code}:{trade_date:%Y%m%d}", "as_of_date": trade_date, "updated_at": now},
        }
