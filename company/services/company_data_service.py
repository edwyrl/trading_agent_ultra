from __future__ import annotations

from datetime import UTC, date, datetime
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from company.constants import DAILY_STOCK_TABLE_NAME, MARKET_DATA_TABLE_SCHEMA, STOCK_FINANCIAL_TABLE_NAME
from contracts.enums import SwLevel

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CompanyDataService:
    def __init__(
        self,
        session: Session | None = None,
        *,
        table_schema: str | None = None,
        daily_table_name: str | None = None,
        financial_table_name: str | None = None,
    ):
        self.session = session
        self.table_schema = _safe_identifier(table_schema or MARKET_DATA_TABLE_SCHEMA)
        self.daily_table_name = _safe_identifier(daily_table_name or DAILY_STOCK_TABLE_NAME)
        self.financial_table_name = _safe_identifier(financial_table_name or STOCK_FINANCIAL_TABLE_NAME)

    def fetch_company_bundle(self, ts_code: str, trade_date: date) -> dict:
        """Fetch company bundle from existing stock/financial tables when DB session is provided."""
        now = datetime.now(UTC)
        market_data = self._fetch_market_data(ts_code=ts_code, trade_date=trade_date)
        financial_data = self._fetch_financial_data(ts_code=ts_code, trade_date=trade_date)
        market_ref = self._build_market_ref(ts_code=ts_code, trade_date=trade_date, market_data=market_data, now=now)
        financial_ref = self._build_financial_ref(
            ts_code=ts_code,
            trade_date=trade_date,
            financial_data=financial_data,
            now=now,
        )
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
            "market_data": market_data,
            "financial_data": financial_data,
            "news_texts": [],
            "market_data_ref": market_ref,
            "financial_data_ref": financial_ref,
            "news_data_ref": {"ref_id": f"news:{ts_code}:{trade_date:%Y%m%d}", "as_of_date": trade_date, "updated_at": now},
        }

    def _fetch_market_data(self, *, ts_code: str, trade_date: date) -> dict[str, Any]:
        if self.session is None:
            return {}
        query = text(
            f"""
            SELECT *
            FROM "{self.table_schema}"."{self.daily_table_name}"
            WHERE ts_code = :ts_code AND trade_date = :trade_date
            LIMIT 1
            """
        )
        row = self.session.execute(query, {"ts_code": ts_code, "trade_date": trade_date}).mappings().first()
        return dict(row) if row is not None else {}

    def _fetch_financial_data(self, *, ts_code: str, trade_date: date) -> dict[str, Any]:
        if self.session is None:
            return {}
        query = text(
            f"""
            SELECT *
            FROM "{self.table_schema}"."{self.financial_table_name}"
            WHERE ts_code = :ts_code
              AND ann_date <= :trade_date
            ORDER BY ann_date DESC, end_date DESC
            LIMIT 1
            """
        )
        row = self.session.execute(query, {"ts_code": ts_code, "trade_date": trade_date}).mappings().first()
        return dict(row) if row is not None else {}

    def _build_market_ref(self, *, ts_code: str, trade_date: date, market_data: dict[str, Any], now: datetime) -> dict[str, Any]:
        if market_data:
            return {
                "ref_id": (
                    f"db:{self.table_schema}.{self.daily_table_name}:"
                    f"{ts_code}:{trade_date:%Y%m%d}"
                ),
                "as_of_date": market_data.get("trade_date", trade_date),
                "updated_at": now,
            }
        return {
            "ref_id": (
                f"db:{self.table_schema}.{self.daily_table_name}:"
                f"{ts_code}:missing:{trade_date:%Y%m%d}"
            ),
            "as_of_date": trade_date,
            "updated_at": now,
        }

    def _build_financial_ref(
        self,
        *,
        ts_code: str,
        trade_date: date,
        financial_data: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        if financial_data:
            end_date = financial_data.get("end_date", trade_date)
            ann_date = financial_data.get("ann_date", trade_date)
            end_date_text = end_date.strftime("%Y%m%d") if hasattr(end_date, "strftime") else str(end_date)
            ann_date_text = ann_date.strftime("%Y%m%d") if hasattr(ann_date, "strftime") else str(ann_date)
            return {
                "ref_id": (
                    f"db:{self.table_schema}.{self.financial_table_name}:"
                    f"{ts_code}:{end_date_text}:{ann_date_text}"
                ),
                "as_of_date": end_date,
                "updated_at": now,
            }
        return {
            "ref_id": (
                f"db:{self.table_schema}.{self.financial_table_name}:"
                f"{ts_code}:missing:{trade_date:%Y%m%d}"
            ),
            "as_of_date": trade_date,
            "updated_at": now,
        }


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value}")
    return value
