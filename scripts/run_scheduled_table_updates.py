from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from company.services.tushare_etl_service import TushareETLService, generate_financial_periods
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually run scheduled stock and financial table updates.")
    parser.add_argument(
        "--trade-date",
        dest="trade_date",
        default=date.today().isoformat(),
        help="Trade date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--ts-code",
        dest="ts_code",
        default="",
        help="Optional ts_code filter. Empty means all securities.",
    )
    parser.add_argument(
        "--financial-period",
        dest="financial_periods",
        action="append",
        default=[],
        help="Optional financial period YYYYMMDD. Can be passed multiple times.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    trade_date = date.fromisoformat(args.trade_date)
    ts_code = args.ts_code.strip()
    periods = [item.strip() for item in args.financial_periods if item and item.strip()]
    if not periods:
        periods = generate_financial_periods(trade_date)

    service = TushareETLService.from_settings()
    session = SessionLocal()
    try:
        stock_result = service.sync_stock_price(session, trade_date=trade_date, ts_code=ts_code)
        financial_results = [
            service.sync_financial_data(session, period=period, trade_date=trade_date, ts_code=ts_code)
            for period in periods
        ]
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "status": "success",
                "trade_date": trade_date.isoformat(),
                "stock": asdict(stock_result),
                "financial_periods": periods,
                "financial": [asdict(item) for item in financial_results],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
