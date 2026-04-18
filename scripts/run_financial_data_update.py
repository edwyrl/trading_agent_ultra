from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from company.services.tushare_etl_service import TushareETLService, generate_financial_periods
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update stock financial data table from Tushare.")
    parser.add_argument(
        "--trade-date",
        dest="trade_date",
        default=date.today().isoformat(),
        help="Trade date in YYYY-MM-DD format (used for trade calendar gate).",
    )
    parser.add_argument(
        "--period",
        dest="periods",
        action="append",
        default=[],
        help="Financial period in YYYYMMDD. Can be passed multiple times.",
    )
    parser.add_argument(
        "--ts-code",
        dest="ts_code",
        default="",
        help="Optional ts_code filter. Empty means all securities.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    trade_date = date.fromisoformat(args.trade_date)
    periods = [item.strip() for item in args.periods if item and item.strip()]
    if not periods:
        periods = generate_financial_periods(trade_date)

    if not periods:
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "no_target_periods",
                    "trade_date": trade_date.isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    service = TushareETLService.from_settings()
    session = SessionLocal()
    try:
        results = [
            service.sync_financial_data(
                session,
                period=period,
                trade_date=trade_date,
                ts_code=args.ts_code.strip(),
            )
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
                "periods": periods,
                "results": [asdict(item) for item in results],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
