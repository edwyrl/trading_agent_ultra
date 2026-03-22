from __future__ import annotations

from sqlalchemy.orm import Session

from company.repository import PostgresCompanyRepository
from company.service import CompanyService
from industry.repository import PostgresIndustryRepository
from industry.service import IndustryService
from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator
from integration.linkage_service import MacroIndustryLinkageService
from integration.recheck_executor import IndustryRecheckExecutor
from integration.repository import PostgresIntegrationRepository
from macro.repository import PostgresMacroRepository
from macro.service import MacroService


class Container:
    def __init__(self, session: Session):
        self.session = session

    def macro_service(self) -> MacroService:
        return MacroService(repository=PostgresMacroRepository(self.session))

    def industry_service(self) -> IndustryService:
        return IndustryService(repository=PostgresIndustryRepository(self.session))

    def company_service(self) -> CompanyService:
        return CompanyService(repository=PostgresCompanyRepository(self.session))

    def integration_repository(self) -> PostgresIntegrationRepository:
        return PostgresIntegrationRepository(self.session)

    def macro_industry_linkage_service(self) -> MacroIndustryLinkageService:
        macro_service = self.macro_service()
        integration_repo = self.integration_repository()
        orchestrator = IndustryRecheckOrchestrator(repository=integration_repo)
        return MacroIndustryLinkageService(macro_service=macro_service, orchestrator=orchestrator)

    def industry_recheck_executor(self) -> IndustryRecheckExecutor:
        integration_repo = self.integration_repository()
        industry_service = self.industry_service()
        return IndustryRecheckExecutor(repository=integration_repo, industry_service=industry_service)
