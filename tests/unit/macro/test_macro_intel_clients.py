from __future__ import annotations

import json

import httpx

from contracts.enums import MacroThemeType
from macro.intel.clients import TavilySearchClient
from macro.intel.models import MacroLayer, SearchQuerySpec


class _FakeResponse:
    def __init__(self, body: dict, *, status_code: int = 200):
        self._body = body
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://api.tavily.com/search")
        self.text = json.dumps(body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=self.request,
                response=httpx.Response(status_code=self.status_code, request=self.request, json=self._body),
            )
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


def test_tavily_client_converts_time_range_to_days(monkeypatch) -> None:
    captured: dict = {}

    def _fake_post(url: str, json: dict, timeout: float):  # noqa: ANN001
        captured["payload"] = json
        return _FakeResponse({"results": []})

    monkeypatch.setattr("macro.intel.clients.httpx.post", _fake_post)

    client = TavilySearchClient(
        api_key="key",
        base_url="https://api.tavily.com",
        timeout_seconds=10.0,
        default_params={"topic": "news", "time_range": "3d", "max_results": 5},
        profile_params={},
    )

    _ = client.search(_spec(profile=None))

    assert "time_range" not in captured["payload"]
    assert captured["payload"]["days"] == 3


def test_tavily_client_retries_with_compact_payload_on_400(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_post(url: str, json: dict, timeout: float):  # noqa: ANN001
        calls.append(json)
        if len(calls) == 1:
            return _FakeResponse({"error": "bad request"}, status_code=400)
        return _FakeResponse({"results": []}, status_code=200)

    monkeypatch.setattr("macro.intel.clients.httpx.post", _fake_post)

    client = TavilySearchClient(
        api_key="key",
        base_url="https://api.tavily.com",
        timeout_seconds=10.0,
        default_params={"topic": "news", "time_range": "3d", "max_results": 5},
        profile_params={},
    )

    rows = client.search(_spec(profile=None), include_domains=["federalreserve.gov", "treasury.gov"])

    assert rows == []
    assert len(calls) == 2
    assert "include_domains" in calls[0]
    assert "include_domains" not in calls[1]
