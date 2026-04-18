from __future__ import annotations

from datetime import date

import httpx

from company.services.tushare_etl_service import (
    TushareETLService,
    dedupe_rows_by_update_flag,
    generate_financial_periods,
    merge_financial_rows,
    merge_stock_rows,
)


def _json_response(body: dict) -> httpx.Response:
    request = httpx.Request("POST", "http://api.tushare.pro")
    return httpx.Response(status_code=200, request=request, json=body)


def test_generate_financial_periods_follows_n8n_window() -> None:
    assert generate_financial_periods(date(2026, 3, 10)) == ["20251231"]
    assert generate_financial_periods(date(2026, 4, 10)) == ["20251231", "20260331"]
    assert generate_financial_periods(date(2026, 8, 10)) == ["20260630"]
    assert generate_financial_periods(date(2026, 10, 10)) == ["20260930"]
    assert generate_financial_periods(date(2026, 11, 10)) == []


def test_dedupe_rows_by_update_flag_keeps_latest() -> None:
    rows = [
        {"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 1), "update_flag": 0, "roe": 1},
        {"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 1), "update_flag": 1, "roe": 2},
    ]
    deduped = dedupe_rows_by_update_flag(rows, key_fields=("ts_code", "end_date", "ann_date"))
    assert len(deduped) == 1
    assert deduped[0]["roe"] == 2


def test_merge_stock_rows_reports_orphans() -> None:
    daily_rows = [
        {"ts_code": "000001.SZ", "trade_date": date(2026, 4, 15), "change": 1.2},
        {"ts_code": "000002.SZ", "trade_date": date(2026, 4, 15), "change": 0.2},
    ]
    basic_rows = [
        {"ts_code": "000001.SZ", "trade_date": date(2026, 4, 15), "pe": 20},
        {"ts_code": "000003.SZ", "trade_date": date(2026, 4, 15), "pe": 30},
    ]
    merged, stats = merge_stock_rows(daily_rows=daily_rows, basic_rows=basic_rows)
    assert len(merged) == 2
    assert merged[0]["change_amt"] == 1.2
    assert stats["matched_rows"] == 1
    assert stats["missing_basic_rows"] == 1
    assert stats["orphan_basic_rows"] == 1


def test_merge_financial_rows_left_join_cashflow() -> None:
    cashflow = [
        {"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 20), "n_cashflow_act": 1},
        {"ts_code": "000002.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 20), "n_cashflow_act": 2},
    ]
    income = [{"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 20), "revenue": 10}]
    balance = [{"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 20), "total_assets": 100}]
    indicator = [{"ts_code": "000001.SZ", "end_date": date(2026, 3, 31), "ann_date": date(2026, 4, 20), "roe": 0.12}]
    merged, stats = merge_financial_rows(
        cashflow_rows=cashflow,
        income_rows=income,
        balancesheet_rows=balance,
        fina_indicator_rows=indicator,
    )
    assert len(merged) == 2
    assert merged[0]["revenue"] == 10
    assert merged[1]["revenue"] is None
    assert stats["missing_income_rows"] == 1
    assert stats["missing_balancesheet_rows"] == 1
    assert stats["missing_indicator_rows"] == 1


def test_fetch_api_rows_supports_retry_and_pagination(monkeypatch) -> None:
    calls: list[int] = []

    def _fake_post(url: str, *, json: dict, timeout: float) -> httpx.Response:
        _ = (url, timeout)
        offset = int(json["params"]["offset"])
        calls.append(offset)
        if len(calls) == 1:
            raise httpx.ConnectError("network down", request=httpx.Request("POST", "http://api.tushare.pro"))
        if offset == 0:
            return _json_response(
                {
                    "code": 0,
                    "data": {
                        "fields": ["ts_code", "trade_date"],
                        "items": [["000001.SZ", "20260415"], ["000002.SZ", "20260415"]],
                    },
                }
            )
        return _json_response(
            {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "trade_date"],
                    "items": [["000003.SZ", "20260415"]],
                },
            }
        )

    monkeypatch.setattr("company.services.tushare_etl_service.httpx.post", _fake_post)
    service = TushareETLService(
        api_key="token",
        base_url="http://api.tushare.pro",
        timeout_seconds=5,
        page_size=2,
        retry_max_attempts=3,
        retry_delay_seconds=0,
        max_pages=10,
        table_schema="public",
        daily_table="daily_stock_data",
        financial_table="stock_financial_data",
    )
    rows = service.fetch_api_rows("daily", params={"trade_date": "20260415", "ts_code": ""}, fields=["ts_code", "trade_date"])
    assert len(rows) == 3
    assert calls == [0, 0, 2]
