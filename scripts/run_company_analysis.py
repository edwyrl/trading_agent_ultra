from __future__ import annotations

from datetime import date

from app.container import Container
from shared.db.schema import ensure_schema
from shared.db.session import SessionLocal


def main(ts_code: str = "000001.SZ", trade_date: date | None = None) -> None:
    target_date = trade_date or date.today()
    with SessionLocal() as session:
        ensure_schema(session)
        container = Container(session)
        context = container.company_service().build_company_context(ts_code=ts_code, trade_date=target_date)
        session.commit()
    print(f"context_version={context.context_version}")


if __name__ == "__main__":
    main()
