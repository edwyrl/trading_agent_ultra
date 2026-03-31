from __future__ import annotations

from shared.llm.router import LLMRouter
from shared.llm.registry import LLMRegistry


def _registry() -> LLMRegistry:
    return LLMRegistry.from_dict(
        {
            "models": [
                {"model_id": "openai.a", "provider": "openai", "api_model": "gpt-a"},
                {"model_id": "moonshot.b", "provider": "moonshot", "api_model": "kimi-b"},
            ],
            "roles": {
                "research": {"model_id": "openai.a", "temperature": 0.2},
                "summarize": {"model_id": "moonshot.b"},
            },
        }
    )


def test_router_resolves_by_role() -> None:
    router = LLMRouter(_registry())
    route = router.resolve(role="research")

    assert route.model.model_id == "openai.a"
    assert route.role == "research"
    assert route.role_spec is not None
    assert route.role_spec.temperature == 0.2


def test_router_resolves_explicit_model() -> None:
    router = LLMRouter(_registry())
    route = router.resolve(model_id="moonshot.b")

    assert route.model.model_id == "moonshot.b"
    assert route.role is None
    assert route.role_spec is None
