from __future__ import annotations

from contracts.enums import MacroThemeType
from macro.intel.clients import TavilySearchClient
from macro.intel.models import MacroLayer, SearchQuerySpec


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


def _spec(*, profile: str | None) -> SearchQuerySpec:
    return SearchQuerySpec(
        query_id="q-1",
        topic="fiscal_rates",
        layer=MacroLayer.REGULAR,
        query="US Treasury auction deficit debt issuance Treasury yields",
        theme_type=MacroThemeType.OVERSEAS_MAPPING,
        language="en",
        region="US",
        source_profile="INTL",
        tavily_profile=profile,
    )


def test_tavily_client_uses_profile_params(monkeypatch) -> None:
    captured: dict = {}

    def _fake_post(url: str, json: dict, timeout: float):  # noqa: ANN001
        captured["url"] = url
        captured["payload"] = json
        captured["timeout"] = timeout
        return _FakeResponse({"results": []})

    monkeypatch.setattr("macro.intel.clients.httpx.post", _fake_post)

    client = TavilySearchClient(
        api_key="key",
        base_url="https://api.tavily.com",
        timeout_seconds=10.0,
        default_params={"topic": "news", "max_results": 5},
        profile_params={"finance": {"topic": "finance", "max_results": 3}},
    )

    rows = client.search(_spec(profile="finance"))

    assert rows == []
    assert captured["payload"]["topic"] == "finance"
    assert captured["payload"]["max_results"] == 3


def test_tavily_client_falls_back_to_default_params(monkeypatch) -> None:
    captured: dict = {}

    def _fake_post(url: str, json: dict, timeout: float):  # noqa: ANN001
        captured["payload"] = json
        return _FakeResponse({"results": []})

    monkeypatch.setattr("macro.intel.clients.httpx.post", _fake_post)

    client = TavilySearchClient(
        api_key="key",
        base_url="https://api.tavily.com",
        timeout_seconds=10.0,
        default_params={"topic": "news", "max_results": 5},
        profile_params={"finance": {"topic": "finance", "max_results": 3}},
    )

    rows = client.search(_spec(profile="news"))

    assert rows == []
    assert captured["payload"]["topic"] == "news"
    assert captured["payload"]["max_results"] == 5
