from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DailySnapshotRow:
    ts_code: str
    close: float
    pre_close: float
    pct_chg: float
    amount: float
    vol: float
    turnover_rate: float


class MarketDataProvider(Protocol):
    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]: ...

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]: ...

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]: ...


class PostgresMarketDataProvider:
    def __init__(
        self,
        session: Session,
        *,
        table_schema: str = "public",
        daily_table: str = "daily_stock_data",
    ):
        self.session = session
        self.table_schema = table_schema
        self.daily_table = daily_table

    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]:
        rows = self.session.execute(
            text(
                f"""
                SELECT DISTINCT trade_date
                FROM "{self.table_schema}"."{self.daily_table}"
                WHERE trade_date BETWEEN :start_date AND :end_date
                ORDER BY trade_date ASC
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        ).fetchall()
        return [row[0] for row in rows]

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]:
        rows = self.session.execute(
            text(
                f"""
                SELECT ts_code, close, pre_close, pct_chg, amount, vol, turnover_rate
                FROM "{self.table_schema}"."{self.daily_table}"
                WHERE trade_date = :trade_date
                ORDER BY ts_code
                """
            ),
            {"trade_date": as_of_date},
        ).fetchall()
        return [
            DailySnapshotRow(
                ts_code=str(row[0]),
                close=_to_float(row[1]),
                pre_close=_to_float(row[2]),
                pct_chg=_to_float(row[3]),
                amount=_to_float(row[4]),
                vol=_to_float(row[5]),
                turnover_rate=_to_float(row[6]),
            )
            for row in rows
        ]

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]:
        rows = self.session.execute(
            text(
                f"""
                SELECT trade_date, AVG(pct_chg) AS avg_pct_chg
                FROM "{self.table_schema}"."{self.daily_table}"
                WHERE trade_date BETWEEN :start_date AND :end_date
                  AND pct_chg IS NOT NULL
                GROUP BY trade_date
                ORDER BY trade_date ASC
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        ).fetchall()
        return {row[0]: _to_float(row[1]) / 100.0 for row in rows}


def _to_float(value: Decimal | float | int | str | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0
