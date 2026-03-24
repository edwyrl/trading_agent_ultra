from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from macro.intel.models import RawArticle, SearchEngine, SearchQuerySpec
from shared.logging import get_logger


class SearchClient(Protocol):
    def search(self, spec: SearchQuerySpec, *, include_domains: list[str] | None = None) -> list[RawArticle]: ...


class TavilySearchClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        default_params: dict[str, Any] | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.default_params = default_params or {}
        self.logger = get_logger(__name__)

    def search(self, spec: SearchQuerySpec, *, include_domains: list[str] | None = None) -> list[RawArticle]:
        if not self.api_key:
            self.logger.warning("tavily_api_key_missing query_id=%s", spec.query_id)
            return []

        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": spec.query,
            **self.default_params,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        try:
            resp = httpx.post(
                _search_url(self.base_url),
                json=payload,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:  # pragma: no cover - network/runtime safety
            self.logger.error("tavily_search_failed query_id=%s error=%s", spec.query_id, exc)
            return []

        results = body.get("results", []) if isinstance(body, dict) else []
        articles: list[RawArticle] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            if not title or not url:
                continue
            content = str(row.get("content") or row.get("raw_content") or "")
            published_at = _parse_datetime(row.get("published_date") or row.get("published_at"))
            articles.append(
                RawArticle.from_web_result(
                    engine=SearchEngine.TAVILY,
                    spec=spec,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                    language=spec.language,
                    source_name=row.get("source") if isinstance(row.get("source"), str) else None,
                    raw_score=_to_float(row.get("score")),
                )
            )
        return articles


class BochaSearchClient:
    """Generic Bocha adapter. Endpoint/headers are config-driven for compatibility with local account setup."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        default_params: dict[str, Any] | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.default_params = default_params or {}
        self.logger = get_logger(__name__)

    def search(self, spec: SearchQuerySpec, *, include_domains: list[str] | None = None) -> list[RawArticle]:
        if not self.api_key:
            self.logger.warning("bocha_api_key_missing query_id=%s", spec.query_id)
            return []

        payload: dict[str, Any] = {
            "query": spec.query,
            **self.default_params,
        }
        if include_domains:
            payload["site_filter"] = include_domains

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = httpx.post(
                self.base_url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:  # pragma: no cover - network/runtime safety
            self.logger.error("bocha_search_failed query_id=%s error=%s", spec.query_id, exc)
            return []

        rows = _extract_rows(body)
        articles: list[RawArticle] = []
        for row in rows:
            title = str(row.get("title") or row.get("name") or "").strip()
            url = str(row.get("url") or row.get("link") or "").strip()
            if not title or not url:
                continue
            content = str(row.get("snippet") or row.get("content") or "")
            published_at = _parse_datetime(row.get("published_at") or row.get("published_time") or row.get("date"))
            articles.append(
                RawArticle.from_web_result(
                    engine=SearchEngine.BOCHA,
                    spec=spec,
                    title=title,
                    url=url,
                    content=content,
                    published_at=published_at,
                    language=spec.language,
                    source_name=row.get("source") if isinstance(row.get("source"), str) else None,
                    raw_score=_to_float(row.get("score")),
                )
            )
        return articles


def _extract_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if not isinstance(body, dict):
        return []

    candidates = [
        body.get("results"),
        body.get("items"),
        body.get("data"),
        (body.get("data") or {}).get("items") if isinstance(body.get("data"), dict) else None,
        (body.get("data") or {}).get("results") if isinstance(body.get("data"), dict) else None,
        (body.get("data") or {}).get("webPages", {}).get("value")
        if isinstance(body.get("data"), dict) and isinstance((body.get("data") or {}).get("webPages"), dict)
        else None,
        body.get("webPages", {}).get("value") if isinstance(body.get("webPages"), dict) else None,
    ]
    for c in candidates:
        if isinstance(c, list):
            return [x for x in c if isinstance(x, dict)]
    return []


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _search_url(base_url: str) -> str:
    return base_url if base_url.endswith("/search") else f"{base_url}/search"
