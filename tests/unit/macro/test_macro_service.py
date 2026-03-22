from __future__ import annotations

from macro.service import MacroService


def test_macro_service_init() -> None:
    service = MacroService(repository=None)  # type: ignore[arg-type]
    assert service is not None
