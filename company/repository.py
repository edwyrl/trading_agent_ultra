from __future__ import annotations

from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from company.models import CompanyAnalysisRunModel, CompanyAnalystOutputModel, CompanyContextSnapshotModel
from contracts.company_contracts import CompanyContextDTO


class CompanyRepository(Protocol):
    def save_company_context(self, context: CompanyContextDTO) -> None: ...

    def get_latest_context(self, ts_code: str, trade_date: date | None = None) -> CompanyContextDTO | None: ...

    def save_analysis_run(self, payload: dict) -> None: ...

    def save_analyst_output(self, payload: dict) -> None: ...


class PostgresCompanyRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_company_context(self, context: CompanyContextDTO) -> None:
        row = CompanyContextSnapshotModel(
            version=context.version,
            ts_code=context.ts_code,
            trade_date=context.trade_date,
            industry_id=context.sw_l3_id or context.sw_l2_id or context.sw_l1_id,
            macro_version_ref=context.macro_context_ref.version,
            industry_version_ref=context.industry_thesis_ref.version,
            payload=context.model_dump(mode="json"),
        )
        self.session.add(row)

    def get_latest_context(self, ts_code: str, trade_date: date | None = None) -> CompanyContextDTO | None:
        query = select(CompanyContextSnapshotModel).where(CompanyContextSnapshotModel.ts_code == ts_code)
        if trade_date:
            query = query.where(CompanyContextSnapshotModel.trade_date <= trade_date)
        row = self.session.execute(query.order_by(CompanyContextSnapshotModel.trade_date.desc())).scalars().first()
        if not row:
            return None
        return CompanyContextDTO.model_validate(row.payload)

    def save_analysis_run(self, payload: dict) -> None:
        self.session.add(CompanyAnalysisRunModel(**payload))

    def save_analyst_output(self, payload: dict) -> None:
        self.session.add(CompanyAnalystOutputModel(**payload))
