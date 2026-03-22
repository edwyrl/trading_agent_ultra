from __future__ import annotations

from industry.repository import PostgresIndustryRepository
from industry.service import IndustryService
from integration.recheck_executor import IndustryRecheckExecutor
from integration.repository import PostgresIntegrationRepository
from shared.db.schema import ensure_schema
from shared.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        ensure_schema(session)
        integration_repo = PostgresIntegrationRepository(session)
        industry_service = IndustryService(repository=PostgresIndustryRepository(session))
        executor = IndustryRecheckExecutor(repository=integration_repo, industry_service=industry_service)

        stats = executor.run_pending()
        session.commit()

    print(stats)


if __name__ == "__main__":
    main()
