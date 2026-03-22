from __future__ import annotations

from contracts.confidence import ConfidenceDTO
from contracts.enums import ConfidenceLevel


def normalize_confidence(score: float) -> ConfidenceDTO:
    if score < 0.4:
        level = ConfidenceLevel.LOW
    elif score < 0.7:
        level = ConfidenceLevel.MEDIUM
    else:
        level = ConfidenceLevel.HIGH

    return ConfidenceDTO(score=score, level=level)
