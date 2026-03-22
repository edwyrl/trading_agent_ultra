from __future__ import annotations

from contracts.enums import ConfidenceLevel
from integration.contract_adapters import normalize_confidence


def test_normalize_confidence() -> None:
    assert normalize_confidence(0.2).level == ConfidenceLevel.LOW
    assert normalize_confidence(0.5).level == ConfidenceLevel.MEDIUM
    assert normalize_confidence(0.8).level == ConfidenceLevel.HIGH
