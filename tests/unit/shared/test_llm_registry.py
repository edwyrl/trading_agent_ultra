from __future__ import annotations

from pathlib import Path

import pytest

from shared.llm.models import LLMProvider
from shared.llm.registry import LLMRegistry


def test_registry_loads_default_yaml() -> None:
    path = Path("shared/config/llm_models.yaml")
    registry = LLMRegistry.from_yaml(path)

    research_role = registry.get_role("research")
    model = registry.get_model(research_role.model_id)

    assert model.provider == LLMProvider.OPENAI
    assert "reasoning" in model.capabilities


def test_registry_rejects_unknown_model_for_role() -> None:
    with pytest.raises(ValueError, match="unknown model"):
        LLMRegistry.from_dict(
            {
                "models": [
                    {
                        "model_id": "openai.test",
                        "provider": "openai",
                        "api_model": "gpt-test",
                    }
                ],
                "roles": {
                    "research": {
                        "model_id": "openai.missing",
                    }
                },
            }
        )
