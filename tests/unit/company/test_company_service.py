from __future__ import annotations

from company.service import CompanyService


def test_company_service_init() -> None:
    service = CompanyService(repository=None)  # type: ignore[arg-type]
    assert service is not None
