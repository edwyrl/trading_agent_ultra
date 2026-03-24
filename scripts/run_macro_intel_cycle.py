from __future__ import annotations

import argparse
import json
from datetime import date

from app.container import Container
from macro.intel.pipeline import MacroIntelPipeline
from macro.retriever import MacroRetriever
from macro.service import MacroService
from macro.updater import MacroUpdater
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run macro cycle with tavily+bocha intel pipeline.")
    parser.add_argument("--date", dest="as_of_date", default=date.today().isoformat(), help="As-of date (YYYY-MM-DD).")
    parser.add_argument("--intel-config", dest="intel_config", default=None, help="Optional path to macro intel YAML.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    as_of_date = date.fromisoformat(args.as_of_date)

    with SessionLocal() as session:
        container = Container(session=session)
        base_service = container.macro_service()
        pipeline = MacroIntelPipeline.from_settings(config_path=args.intel_config)

        service = MacroService(
            repository=base_service.repository,
            updater=MacroUpdater(
                repository=base_service.repository,
                retriever=MacroRetriever(intel_pipeline=pipeline),
                mapper=base_service.updater.mapper,
                triggers=base_service.updater.triggers,
            ),
        )

        master = service.run_daily_incremental_update(as_of_date=as_of_date, events=None)
        session.commit()

    print(
        json.dumps(
            {
                "version": master.version,
                "as_of_date": master.as_of_date.isoformat(),
                "biases": [b.value for b in master.current_macro_bias],
                "material_change": master.material_change.material_change,
                "material_level": master.material_change.level.value,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
