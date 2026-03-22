from __future__ import annotations

from sqlalchemy.orm import Session

from company.repository import PostgresCompanyRepository
from company.service import CompanyService
from industry.repository import PostgresIndustryRepository
from industry.service import IndustryService
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
