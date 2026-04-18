from __future__ import annotations

from datetime import date

from company.services.company_data_service import CompanyDataService


class _FakeResult:
    def __init__(self, row: dict | None):
        self._row = row

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> dict | None:
        return self._row


class _FakeSession:
    def __init__(self, *, market_row: dict | None, financial_row: dict | None):
        self.market_row = market_row
        self.financial_row = financial_row
        self.calls: list[str] = []

    def execute(self, stmt, params):  # type: ignore[no-untyped-def]
        _ = params
        sql = str(stmt)
        self.calls.append(sql)
        if "daily_stock_data" in sql:
            return _FakeResult(self.market_row)
        return _FakeResult(self.financial_row)


def test_fetch_company_bundle_uses_db_rows_when_available() -> None:
    session = _FakeSession(
        market_row={"ts_code": "000001.SZ", "trade_date": date(2026, 4, 15), "close": 12.3},
        financial_row={
            "ts_code": "000001.SZ",
            "end_date": date(2026, 3, 31),
            "ann_date": date(2026, 4, 12),
            "roe": 0.12,
        },
    )
    service = CompanyDataService(session=session, table_schema="public")
    bundle = service.fetch_company_bundle("000001.SZ", date(2026, 4, 15))
    assert bundle["market_data"]["close"] == 12.3
    assert bundle["financial_data"]["roe"] == 0.12
    assert bundle["market_data_ref"]["ref_id"].startswith("db:public.daily_stock_data:000001.SZ")
    assert bundle["financial_data_ref"]["ref_id"].startswith("db:public.stock_financial_data:000001.SZ")


def test_fetch_company_bundle_returns_empty_when_market_missing() -> None:
    session = _FakeSession(
        market_row=None,
        financial_row=None,
    )
    service = CompanyDataService(session=session, table_schema="public")
    bundle = service.fetch_company_bundle("000001.SZ", date(2026, 4, 15))
    assert bundle["market_data"] == {}
    assert bundle["financial_data"] == {}
    assert "missing" in bundle["market_data_ref"]["ref_id"]
    assert "missing" in bundle["financial_data_ref"]["ref_id"]
