from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from contracts.confidence import ConfidenceDTO
from contracts.enums import ConfidenceLevel, MacroBiasTag
from contracts.macro_contracts import MacroConstraintsSummaryDTO
from contracts.material_change import MaterialChangeDTO


@pytest.mark.parametrize(
    "score,level",
    [
        (0.2, ConfidenceLevel.LOW),
        (0.6, ConfidenceLevel.MEDIUM),
        (0.9, ConfidenceLevel.HIGH),
    ],
)
def test_confidence_dto(score: float, level: ConfidenceLevel) -> None:
    dto = ConfidenceDTO(score=score, level=level)
    assert dto.score == score


def test_macro_constraints_bias_limit() -> None:
    with pytest.raises(Exception):
        MacroConstraintsSummaryDTO(
            version="v1",
            as_of_date=date(2026, 3, 22),
            current_macro_bias=[
                MacroBiasTag.LIQUIDITY_DOMINANT,
                MacroBiasTag.POLICY_EXPECTATION_DOMINANT,
                MacroBiasTag.FUNDAMENTAL_VALIDATION_DOMINANT,
                MacroBiasTag.RISK_APPETITE_RECOVERY,
            ],
            macro_mainline="test",
            style_impact="test",
            material_change=MaterialChangeDTO(material_change=False, level="NONE", reasons=[]),
            confidence=ConfidenceDTO(score=0.5, level=ConfidenceLevel.MEDIUM),
        )


def test_material_change_required_bool() -> None:
    dto = MaterialChangeDTO(material_change=True, level="HIGH", reasons=["x"])
    assert dto.material_change is True
    assert dto.level == "HIGH"


def test_datetime_keeps_timezone() -> None:
    now = datetime.now(UTC)
    assert now.tzinfo is UTC
