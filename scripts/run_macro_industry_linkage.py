from __future__ import annotations

from datetime import date

from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator
from integration.linkage_service import MacroIndustryLinkageService
from integration.repository import PostgresIntegrationRepository
from macro.repository import PostgresMacroRepository
from macro.service import MacroService
from shared.db.schema import ensure_schema
from shared.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        ensure_schema(session)
        macro_service = MacroService(repository=PostgresMacroRepository(session))
        integration_repo = PostgresIntegrationRepository(session)
        orchestrator = IndustryRecheckOrchestrator(repository=integration_repo)
        linkage_service = MacroIndustryLinkageService(macro_service=macro_service, orchestrator=orchestrator)

        queued = linkage_service.enqueue_from_recent_deltas(since_date=date.today())
        session.commit()

    print(f"queued_items={len(queued)}")


if __name__ == "__main__":
    main()
