from __future__ import annotations

from industry.service import IndustryService


def test_industry_service_init() -> None:
    service = IndustryService(repository=None)  # type: ignore[arg-type]
    assert service is not None
