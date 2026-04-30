from __future__ import annotations

import argparse
import json
from datetime import date

from app.container import Container
from contracts.signals_contracts import SignalDateRangeDTO, SignalRunRequestDTO
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit a signal run into async queue.")
    parser.add_argument("--signal-key", default="liquidity_concentration")
    parser.add_argument("--start-date", default=(date.today().replace(day=1)).isoformat())
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--config-json", default="{}", help="JSON string for plugin config overrides")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    with SessionLocal() as session:
        container = Container(session=session)
        service = container.signal_service()
        request = SignalRunRequestDTO(
            signal_key=args.signal_key,
            date_range=SignalDateRangeDTO(
                start_date=date.fromisoformat(args.start_date),
                end_date=date.fromisoformat(args.end_date),
            ),
            config=json.loads(args.config_json),
        )
        status = service.submit_run(request)
        session.commit()

    print(json.dumps(status.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
