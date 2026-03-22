from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from app.container import Container
from macro.retriever import MacroEvent
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run macro daily incremental update.")
    parser.add_argument("--date", dest="as_of_date", default=date.today().isoformat(), help="As-of date (YYYY-MM-DD).")
    parser.add_argument(
        "--events-file",
        dest="events_file",
        default=None,
        help="Optional JSON file containing a list of macro events.",
    )
    return parser.parse_args()


def _load_events(path: str | None) -> list[MacroEvent] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("events-file must be a JSON array.")
    return [MacroEvent.model_validate(item) for item in payload]


def main() -> None:
    args = _parse_args()
    as_of_date = date.fromisoformat(args.as_of_date)
    events = _load_events(args.events_file)

    session = SessionLocal()
    try:
        container = Container(session=session)
        master = container.macro_service().run_daily_incremental_update(as_of_date=as_of_date, events=events)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "version": master.version,
                "as_of_date": master.as_of_date.isoformat(),
                "material_change": master.material_change.material_change,
                "material_level": master.material_change.level.value,
                "biases": [bias.value for bias in master.current_macro_bias],
                "key_changes": master.key_changes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
