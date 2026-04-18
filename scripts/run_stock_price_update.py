from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import json

from company.services.tushare_etl_service import TushareETLService
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update daily stock price table from Tushare.")
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
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    trade_date = date.fromisoformat(args.trade_date)
    service = TushareETLService.from_settings()

    session = SessionLocal()
    try:
        result = service.sync_stock_price(session, trade_date=trade_date, ts_code=args.ts_code.strip())
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
