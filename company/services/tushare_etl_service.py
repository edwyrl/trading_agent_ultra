from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any

import httpx
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from company.constants import DAILY_STOCK_TABLE_NAME, MARKET_DATA_TABLE_SCHEMA, STOCK_FINANCIAL_TABLE_NAME
from shared.config import settings
from shared.logging import get_logger
from shared.retry import RetryExhaustedError, run_with_retry

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DAILY_FIELDS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
]

DAILY_BASIC_FIELDS = [
    "ts_code",
    "trade_date",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
]

INCOME_FIELDS = [
    "ts_code",
    "end_date",
    "ann_date",
    "update_flag",
    "revenue",
    "non_oper_income",
    "n_income",
    "n_income_attr_p",
    "operate_profit",
    "total_profit",
    "oper_cost",
    "oper_exp",
    "admin_exp",
    "fin_exp",
    "rd_exp",
]

BALANCESHEET_FIELDS = [
    "ts_code",
    "end_date",
    "ann_date",
    "update_flag",
    "total_assets",
    "total_liab",
    "total_hldr_eqy_exc_min_int",
    "total_cur_assets",
    "total_nca",
    "total_cur_liab",
    "total_ncl",
    "money_cap",
    "accounts_receiv",
    "inventories",
    "fix_assets",
]

FINA_INDICATOR_FIELDS = [
    "ts_code",
    "end_date",
    "ann_date",
    "update_flag",
    "roe",
    "roa",
    "roe_waa",
    "roe_dt",
    "roa2",
    "gross_margin",
    "netprofit_margin",
    "cogs_of_sales",
    "expense_of_sales",
    "profit_to_gr",
    "saleexp_to_gr",
    "adminexp_of_gr",
    "finaexp_of_gr",
    "debt_to_assets",
    "assets_to_eqt",
    "dp_assets_to_eqt",
    "ca_to_assets",
    "nca_to_assets",
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
]

CASHFLOW_FIELDS = [
    "ts_code",
    "end_date",
    "ann_date",
    "update_flag",
    "n_cashflow_act",
    "n_cashflow_inv_act",
    "n_cash_flows_fnc_act",
    "c_cash_equ_end_period",
    "c_cash_equ_beg_period",
]

DAILY_TARGET_COLUMNS = [
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change_amt",
    "pct_chg",
    "vol",
    "amount",
    "turnover_rate",
    "turnover_rate_f",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "dv_ttm",
    "total_share",
    "float_share",
    "free_share",
    "total_mv",
    "circ_mv",
    "change",
]

FINANCIAL_TARGET_COLUMNS = [
    "ts_code",
    "end_date",
    "ann_date",
    "n_cashflow_act",
    "n_cashflow_inv_act",
    "n_cash_flows_fnc_act",
    "c_cash_equ_end_period",
    "c_cash_equ_beg_period",
    "revenue",
    "non_oper_income",
    "n_income",
    "n_income_attr_p",
    "operate_profit",
    "total_profit",
    "oper_cost",
    "oper_exp",
    "admin_exp",
    "fin_exp",
    "rd_exp",
    "total_assets",
    "total_liab",
    "total_hldr_eqy_exc_min_int",
    "total_cur_assets",
    "total_nca",
    "total_cur_liab",
    "total_ncl",
    "money_cap",
    "accounts_receiv",
    "inventories",
    "fix_assets",
    "roe",
    "roa",
    "roe_waa",
    "roe_dt",
    "roa2",
    "gross_margin",
    "netprofit_margin",
    "cogs_of_sales",
    "expense_of_sales",
    "profit_to_gr",
    "saleexp_to_gr",
    "adminexp_of_gr",
    "finaexp_of_gr",
    "debt_to_assets",
    "assets_to_eqt",
    "dp_assets_to_eqt",
    "ca_to_assets",
    "nca_to_assets",
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
]


def generate_financial_periods(as_of_date: date) -> list[str]:
    year = as_of_date.year
    month = as_of_date.month
    if month == 3:
        return [f"{year - 1}1231"]
    if month == 4:
        return [f"{year - 1}1231", f"{year}0331"]
    if month in {7, 8}:
        return [f"{year}0630"]
    if month == 10:
        return [f"{year}0930"]
    return []


def dedupe_rows_by_update_flag(
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
    update_flag_field: str = "update_flag",
) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row.get(field) for field in key_fields)
        existing = unique.get(key)
        if existing is None:
            unique[key] = row
            continue
        current_flag = _to_float(row.get(update_flag_field)) or 0.0
        existing_flag = _to_float(existing.get(update_flag_field)) or 0.0
        if current_flag > existing_flag:
            unique[key] = row
    return list(unique.values())


def merge_stock_rows(
    *,
    daily_rows: list[dict[str, Any]],
    basic_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    key_fields = ("ts_code", "trade_date")
    basic_index = {tuple(row.get(k) for k in key_fields): row for row in basic_rows}
    merged_rows: list[dict[str, Any]] = []
    matched = 0
    missing_basic = 0
    for daily_row in daily_rows:
        key = tuple(daily_row.get(k) for k in key_fields)
        row = dict(daily_row)
        basic_row = basic_index.get(key)
        if basic_row is None:
            missing_basic += 1
        else:
            row.update(basic_row)
            matched += 1
        if row.get("change_amt") is None and row.get("change") is not None:
            row["change_amt"] = row["change"]
        merged_rows.append({column: row.get(column) for column in DAILY_TARGET_COLUMNS})
    return merged_rows, {
        "matched_rows": matched,
        "missing_basic_rows": missing_basic,
        "orphan_basic_rows": max(len(basic_rows) - matched, 0),
    }


def merge_financial_rows(
    *,
    cashflow_rows: list[dict[str, Any]],
    income_rows: list[dict[str, Any]],
    balancesheet_rows: list[dict[str, Any]],
    fina_indicator_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    key_fields = ("ts_code", "end_date", "ann_date")
    income_index = {tuple(row.get(k) for k in key_fields): row for row in income_rows}
    balancesheet_index = {tuple(row.get(k) for k in key_fields): row for row in balancesheet_rows}
    fina_indicator_index = {tuple(row.get(k) for k in key_fields): row for row in fina_indicator_rows}

    merged_rows: list[dict[str, Any]] = []
    missing_income = 0
    missing_balancesheet = 0
    missing_indicator = 0
    matched_income = 0
    matched_balancesheet = 0
    matched_indicator = 0

    for base in cashflow_rows:
        key = tuple(base.get(k) for k in key_fields)
        merged = dict(base)
        income = income_index.get(key)
        if income:
            merged.update(income)
            matched_income += 1
        else:
            missing_income += 1
        balancesheet = balancesheet_index.get(key)
        if balancesheet:
            merged.update(balancesheet)
            matched_balancesheet += 1
        else:
            missing_balancesheet += 1
        indicator = fina_indicator_index.get(key)
        if indicator:
            merged.update(indicator)
            matched_indicator += 1
        else:
            missing_indicator += 1
        merged_rows.append({column: merged.get(column) for column in FINANCIAL_TARGET_COLUMNS})

    return merged_rows, {
        "matched_income_rows": matched_income,
        "missing_income_rows": missing_income,
        "matched_balancesheet_rows": matched_balancesheet,
        "missing_balancesheet_rows": missing_balancesheet,
        "matched_indicator_rows": matched_indicator,
        "missing_indicator_rows": missing_indicator,
        "orphan_income_rows": max(len(income_rows) - matched_income, 0),
        "orphan_balancesheet_rows": max(len(balancesheet_rows) - matched_balancesheet, 0),
        "orphan_indicator_rows": max(len(fina_indicator_rows) - matched_indicator, 0),
    }


@dataclass
class SyncResult:
    status: str
    table_name: str
    rows_upserted: int
    fetch_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class TushareETLService:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        page_size: int,
        retry_max_attempts: int,
        retry_delay_seconds: float,
        max_pages: int,
        table_schema: str = MARKET_DATA_TABLE_SCHEMA,
        daily_table: str = DAILY_STOCK_TABLE_NAME,
        financial_table: str = STOCK_FINANCIAL_TABLE_NAME,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.page_size = max(1, page_size)
        self.retry_max_attempts = max(1, retry_max_attempts)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.max_pages = max(1, max_pages)
        self.table_schema = _safe_identifier(table_schema)
        self.daily_table = _safe_identifier(daily_table)
        self.financial_table = _safe_identifier(financial_table)
        self.logger = get_logger(__name__)

    @classmethod
    def from_settings(cls) -> "TushareETLService":
        return cls(
            api_key=settings.tushare_api_key,
            base_url=settings.tushare_base_url,
            timeout_seconds=settings.tushare_timeout_seconds,
            page_size=settings.tushare_page_size,
            retry_max_attempts=settings.tushare_retry_max_attempts,
            retry_delay_seconds=settings.tushare_retry_delay_seconds,
            max_pages=settings.tushare_max_pages,
        )

    def is_trade_day(self, trade_date: date) -> bool:
        trade_date_str = trade_date.strftime("%Y%m%d")
        rows = self.fetch_api_rows(
            "trade_cal",
            params={"exchange": "SSE", "start_date": trade_date_str, "end_date": trade_date_str},
            fields=["is_open"],
        )
        if not rows:
            return False
        value = rows[0].get("is_open")
        return str(value).strip() == "1"

    def sync_stock_price(self, session: Session, *, trade_date: date, ts_code: str = "") -> SyncResult:
        if not self.is_trade_day(trade_date):
            return SyncResult(
                status="skipped",
                table_name=f"{self.table_schema}.{self.daily_table}",
                rows_upserted=0,
                warnings=[f"{trade_date.isoformat()} is not a trade day, stock update skipped."],
                meta={"trade_date": trade_date.isoformat()},
            )

        trade_date_str = trade_date.strftime("%Y%m%d")
        daily_raw, daily_warning = self._fetch_endpoint_rows(
            api_name="daily",
            params={"trade_date": trade_date_str, "ts_code": ts_code},
            fields=DAILY_FIELDS,
            endpoint_label="daily",
        )
        basic_raw, basic_warning = self._fetch_endpoint_rows(
            api_name="daily_basic",
            params={"trade_date": trade_date_str, "ts_code": ts_code},
            fields=DAILY_BASIC_FIELDS,
            endpoint_label="daily_basic",
        )

        daily_rows = dedupe_rows_by_update_flag(
            _normalize_rows(daily_raw, date_fields=("trade_date",)),
            key_fields=("ts_code", "trade_date"),
        )
        basic_rows = dedupe_rows_by_update_flag(
            _normalize_rows(basic_raw, date_fields=("trade_date",)),
            key_fields=("ts_code", "trade_date"),
        )
        merged_rows, merge_stats = merge_stock_rows(daily_rows=daily_rows, basic_rows=basic_rows)
        if merged_rows:
            ensure_month_partition(
                session=session,
                schema=self.table_schema,
                parent_table=self.daily_table,
                partition_date=trade_date,
                partition_column="trade_date",
            )
            upsert_rows(
                session=session,
                schema=self.table_schema,
                table_name=self.daily_table,
                rows=merged_rows,
                match_columns=("ts_code", "trade_date"),
            )
        warnings = []
        if daily_warning:
            warnings.append(daily_warning)
        if basic_warning:
            warnings.append(basic_warning)
        if merge_stats["missing_basic_rows"] > 0:
            warnings.append(f"daily_basic missing for {merge_stats['missing_basic_rows']} rows.")
        if merge_stats["orphan_basic_rows"] > 0:
            warnings.append(f"daily_basic orphan rows={merge_stats['orphan_basic_rows']}.")

        return SyncResult(
            status="success",
            table_name=f"{self.table_schema}.{self.daily_table}",
            rows_upserted=len(merged_rows),
            fetch_counts={"daily": len(daily_rows), "daily_basic": len(basic_rows)},
            warnings=warnings,
            meta={
                "trade_date": trade_date.isoformat(),
                "merge_stats": merge_stats,
            },
        )

    def sync_financial_data(
        self,
        session: Session,
        *,
        period: str,
        trade_date: date,
        ts_code: str = "",
    ) -> SyncResult:
        if not self.is_trade_day(trade_date):
            return SyncResult(
                status="skipped",
                table_name=f"{self.table_schema}.{self.financial_table}",
                rows_upserted=0,
                warnings=[f"{trade_date.isoformat()} is not a trade day, financial update skipped."],
                meta={"period": period, "trade_date": trade_date.isoformat()},
            )

        params = {"period": period, "ts_code": ts_code}
        cashflow_raw, cashflow_warning = self._fetch_endpoint_rows(
            api_name="cashflow_vip",
            params=params,
            fields=CASHFLOW_FIELDS,
            endpoint_label="cashflow_vip",
        )
        income_raw, income_warning = self._fetch_endpoint_rows(
            api_name="income_vip",
            params=params,
            fields=INCOME_FIELDS,
            endpoint_label="income_vip",
        )
        balancesheet_raw, balancesheet_warning = self._fetch_endpoint_rows(
            api_name="balancesheet_vip",
            params=params,
            fields=BALANCESHEET_FIELDS,
            endpoint_label="balancesheet_vip",
        )
        fina_indicator_raw, fina_indicator_warning = self._fetch_endpoint_rows(
            api_name="fina_indicator_vip",
            params=params,
            fields=FINA_INDICATOR_FIELDS,
            endpoint_label="fina_indicator_vip",
        )

        key_fields = ("ts_code", "end_date", "ann_date")
        normalized_cashflow = dedupe_rows_by_update_flag(
            _normalize_rows(cashflow_raw, date_fields=("end_date", "ann_date")),
            key_fields=key_fields,
        )
        normalized_income = dedupe_rows_by_update_flag(
            _normalize_rows(income_raw, date_fields=("end_date", "ann_date")),
            key_fields=key_fields,
        )
        normalized_balancesheet = dedupe_rows_by_update_flag(
            _normalize_rows(balancesheet_raw, date_fields=("end_date", "ann_date")),
            key_fields=key_fields,
        )
        normalized_indicator = dedupe_rows_by_update_flag(
            _normalize_rows(fina_indicator_raw, date_fields=("end_date", "ann_date")),
            key_fields=key_fields,
        )

        merged_rows, merge_stats = merge_financial_rows(
            cashflow_rows=normalized_cashflow,
            income_rows=normalized_income,
            balancesheet_rows=normalized_balancesheet,
            fina_indicator_rows=normalized_indicator,
        )

        period_date = _parse_date(period)
        if merged_rows:
            ensure_month_partition(
                session=session,
                schema=self.table_schema,
                parent_table=self.financial_table,
                partition_date=period_date,
                partition_column="end_date",
            )
            upsert_rows(
                session=session,
                schema=self.table_schema,
                table_name=self.financial_table,
                rows=merged_rows,
                match_columns=("ts_code", "end_date", "ann_date"),
            )

        warnings = []
        for warning in [cashflow_warning, income_warning, balancesheet_warning, fina_indicator_warning]:
            if warning:
                warnings.append(warning)
        if merge_stats["missing_income_rows"] > 0:
            warnings.append(f"income_vip missing for {merge_stats['missing_income_rows']} cashflow rows.")
        if merge_stats["missing_balancesheet_rows"] > 0:
            warnings.append(f"balancesheet_vip missing for {merge_stats['missing_balancesheet_rows']} cashflow rows.")
        if merge_stats["missing_indicator_rows"] > 0:
            warnings.append(f"fina_indicator_vip missing for {merge_stats['missing_indicator_rows']} cashflow rows.")

        return SyncResult(
            status="success",
            table_name=f"{self.table_schema}.{self.financial_table}",
            rows_upserted=len(merged_rows),
            fetch_counts={
                "cashflow_vip": len(normalized_cashflow),
                "income_vip": len(normalized_income),
                "balancesheet_vip": len(normalized_balancesheet),
                "fina_indicator_vip": len(normalized_indicator),
            },
            warnings=warnings,
            meta={
                "period": period,
                "trade_date": trade_date.isoformat(),
                "merge_stats": merge_stats,
            },
        )

    def fetch_api_rows(self, api_name: str, *, params: dict[str, Any], fields: list[str]) -> list[dict[str, Any]]:
        if not self.api_key:
            raise ValueError("TUSHARE_API_KEY is empty.")

        all_rows: list[dict[str, Any]] = []
        offset = 0
        pages = 0
        while pages < self.max_pages:
            pages += 1
            body = self._request_with_retry(
                api_name=api_name,
                payload={
                    "api_name": api_name,
                    "token": self.api_key,
                    "params": {**params, "limit": self.page_size, "offset": offset},
                    "fields": ",".join(fields),
                },
            )
            page_rows = _parse_tushare_response(body)
            all_rows.extend(page_rows)
            if len(page_rows) < self.page_size:
                break
            offset += self.page_size

        if pages >= self.max_pages:
            self.logger.warning("tushare_max_pages_reached api=%s pages=%s", api_name, pages)
        return all_rows

    def _request_with_retry(self, *, api_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        def _op() -> dict[str, Any]:
            response = httpx.post(self.base_url, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError(f"{api_name} returned non-object response")
            code = data.get("code")
            if code not in (0, "0", None):
                raise ValueError(f"{api_name} returned code={code}, msg={data.get('msg')}")
            return data

        value, _ = run_with_retry(
            _op,
            operation_name=f"tushare.{api_name}",
            max_attempts=self.retry_max_attempts,
            initial_delay_seconds=self.retry_delay_seconds,
            backoff_factor=1.0,
            retry_exceptions=(httpx.HTTPError, ValueError),
        )
        return value

    def _fetch_endpoint_rows(
        self,
        *,
        api_name: str,
        params: dict[str, Any],
        fields: list[str],
        endpoint_label: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        try:
            return self.fetch_api_rows(api_name, params=params, fields=fields), None
        except (RetryExhaustedError, ValueError, RuntimeError, httpx.HTTPError) as exc:
            warning = f"{endpoint_label} fetch failed, continue with empty rows: {exc}"
            self.logger.error("tushare_endpoint_failed endpoint=%s error=%s", endpoint_label, exc)
            return [], warning


def ensure_month_partition(
    *,
    session: Session,
    schema: str,
    parent_table: str,
    partition_date: date,
    partition_column: str,
) -> None:
    schema_name = _safe_identifier(schema)
    table_name = _safe_identifier(parent_table)
    _ = _safe_identifier(partition_column)
    start_date = partition_date.replace(day=1)
    if start_date.month == 12:
        end_date = start_date.replace(year=start_date.year + 1, month=1)
    else:
        end_date = start_date.replace(month=start_date.month + 1)
    partition_name = f"{table_name}_{start_date:%Y%m}"
    sql = f"""
    CREATE TABLE IF NOT EXISTS "{schema_name}"."{partition_name}"
    PARTITION OF "{schema_name}"."{table_name}"
    FOR VALUES FROM ('{start_date:%Y-%m-%d}')
    TO ('{end_date:%Y-%m-%d}');
    """
    session.execute(text(sql))


def upsert_rows(
    *,
    session: Session,
    schema: str,
    table_name: str,
    rows: list[dict[str, Any]],
    match_columns: tuple[str, ...],
) -> int:
    if not rows:
        return 0
    schema_name = _safe_identifier(schema)
    table_id = _safe_identifier(table_name)
    metadata = MetaData()
    table = Table(table_id, metadata, autoload_with=session.bind, schema=schema_name)
    allowed_columns = {column.name for column in table.columns}
    cleaned_rows = [{k: v for k, v in row.items() if k in allowed_columns} for row in rows]
    stmt = pg_insert(table).values(cleaned_rows)
    update_columns = {column: getattr(stmt.excluded, column) for column in allowed_columns if column not in set(match_columns)}
    upsert_stmt = stmt.on_conflict_do_update(index_elements=list(match_columns), set_=update_columns)
    session.execute(upsert_stmt)
    return len(cleaned_rows)


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"Invalid SQL identifier: {value}")
    return value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return float(text_value)
    except ValueError:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except (InvalidOperation, ValueError):
        return None


def _normalize_rows(rows: list[dict[str, Any]], *, date_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if key in date_fields:
                item[key] = _parse_date(value) if value else None
            elif key == "update_flag":
                item[key] = _to_float(value)
            elif key in {"ts_code"}:
                item[key] = str(value).strip() if value is not None else None
            else:
                item[key] = _to_decimal(value)
        normalized.append(item)
    return normalized


def _parse_tushare_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    code = payload.get("code")
    if code not in (0, "0", None):
        raise RuntimeError(f"Tushare api returned code={code}, msg={payload.get('msg')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, list):
            continue
        result.append({field: row[idx] if idx < len(row) else None for idx, field in enumerate(fields)})
    return result


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    if re.fullmatch(r"\d{8}", text_value):
        return date.fromisoformat(f"{text_value[0:4]}-{text_value[4:6]}-{text_value[6:8]}")
    return date.fromisoformat(text_value)
