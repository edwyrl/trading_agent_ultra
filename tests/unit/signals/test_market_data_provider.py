from __future__ import annotations

from datetime import date
from decimal import Decimal

from signals.services.market_data_provider import DailySnapshotRow, PostgresMarketDataProvider


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, stmt, params):  # type: ignore[no-untyped-def]
        sql = str(stmt)
        self.calls.append(sql)
        if "DISTINCT trade_date" in sql:
            return _FakeResult([(date(2026, 4, 1),), (date(2026, 4, 2),)])
        if "SELECT ts_code, close, pre_close, pct_chg, amount, vol, turnover_rate" in sql:
            return _FakeResult(
                [
                    ("000001.SZ", Decimal("10.5"), Decimal("10.0"), Decimal("1.5"), Decimal("1000"), Decimal("200"), Decimal("3.2")),
                    ("000002.SZ", None, Decimal("8.0"), None, Decimal("0"), None, None),
                ]
            )
        if "AVG(pct_chg)" in sql:
            return _FakeResult([(date(2026, 4, 1), Decimal("1.5")), (date(2026, 4, 2), Decimal("-0.5"))])
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_provider_queries_and_conversions() -> None:
    session = _FakeSession()
    provider = PostgresMarketDataProvider(session=session)

    trade_days = provider.list_trade_days(start_date=date(2026, 4, 1), end_date=date(2026, 4, 10))
    assert trade_days == [date(2026, 4, 1), date(2026, 4, 2)]

    snapshot = provider.fetch_daily_snapshot(as_of_date=date(2026, 4, 1))
    assert snapshot == [
        DailySnapshotRow(ts_code="000001.SZ", close=10.5, pre_close=10.0, pct_chg=1.5, amount=1000.0, vol=200.0, turnover_rate=3.2),
        DailySnapshotRow(ts_code="000002.SZ", close=0.0, pre_close=8.0, pct_chg=0.0, amount=0.0, vol=0.0, turnover_rate=0.0),
    ]

    returns = provider.fetch_market_returns(start_date=date(2026, 4, 1), end_date=date(2026, 4, 2))
    assert returns[date(2026, 4, 1)] == 0.015
    assert returns[date(2026, 4, 2)] == -0.005
