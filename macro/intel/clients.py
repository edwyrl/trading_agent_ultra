from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Protocol

import httpx

from macro.intel.models import RawArticle, SearchEngine, SearchQuerySpec
from shared.logging import get_logger


class SearchClient(Protocol):
    def search(
        self,
        spec: SearchQuerySpec,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawArticle]: ...


class TavilySearchClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout_seconds: float,
        default_params: dict[str, Any] | None = None,
        profile_params: dict[str, dict[str, Any]] | None = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.default_params = default_params or {}
        self.profile_params = profile_params or {}
        self.last_attempt_count = 0
        self.logger = get_logger(__name__)

    def search(
        self,
        spec: SearchQuerySpec,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawArticle]:
        if not self.api_key:
            self.last_attempt_count = 0
            self.logger.warning("tavily_api_key_missing query_id=%s", spec.query_id)
            return []

        payloads = self._build_payload_candidates(
            spec=spec,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
        body: dict[str, Any] | None = None
        last_exc: Exception | None = None
        attempts = 0
        for idx, payload in enumerate(payloads):
            attempts += 1
            try:
                resp = httpx.post(
                    _search_url(self.base_url),
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                resp.raise_for_status()
                raw = resp.json()
                if isinstance(raw, dict):
                    body = raw
                else:
                    body = {"results": []}
                break
            except httpx.HTTPStatusError as exc:  # pragma: no cover - network/runtime safety
                last_exc = exc
                detail = _safe_error_body(exc.response)
                self.logger.warning(
                    "tavily_search_http_error query_id=%s status=%s attempt=%s/%s detail=%s",
                    spec.query_id,
                    exc.response.status_code if exc.response is not None else "unknown",
                    idx + 1,
                    len(payloads),
                    detail,
                )
                # Retry only for likely payload schema mismatch.
                if exc.response is None or exc.response.status_code != 400 or idx >= len(payloads) - 1:
                    break
            except Exception as exc:  # pragma: no cover - network/runtime safety
                last_exc = exc
                self.logger.error(
                    "tavily_search_failed query_id=%s attempt=%s/%s error=%s",
                    spec.query_id,
                    idx + 1,
                    len(payloads),
                    exc,
                )
                break

        self.last_attempt_count = attempts
        if body is None:
            self.logger.error("tavily_search_failed query_id=%s error=%s", spec.query_id, last_exc)
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

    def _resolve_params(self, spec: SearchQuerySpec) -> dict[str, Any]:
        profile = (spec.tavily_profile or "").strip().lower()
        if profile:
            chosen = self.profile_params.get(profile)
            if isinstance(chosen, dict):
                return dict(chosen)
        return dict(self.default_params)

    def _build_payload_candidates(
        self,
        *,
        spec: SearchQuerySpec,
        include_domains: list[str] | None,
        exclude_domains: list[str] | None,
    ) -> list[dict[str, Any]]:
        resolved_params = self._normalize_params(self._resolve_params(spec))
        allowed_domains = _normalize_domains(include_domains)
        if allowed_domains:
            resolved_params["include_domains"] = allowed_domains[:10]
        blocked_domains = _normalize_domains(exclude_domains)
        if blocked_domains:
            resolved_params["exclude_domains"] = blocked_domains[:10]

        primary = {"api_key": self.api_key, "query": spec.query, **resolved_params}
        compact = {
            "api_key": self.api_key,
            "query": spec.query,
            "max_results": int(resolved_params.get("max_results", 5)),
        }
        if "search_depth" in resolved_params:
            compact["search_depth"] = resolved_params["search_depth"]
        if "include_raw_content" in resolved_params:
            compact["include_raw_content"] = resolved_params["include_raw_content"]

        ultra_compact = {
            "api_key": self.api_key,
            "query": spec.query,
            "max_results": int(resolved_params.get("max_results", 5)),
        }
        return [primary, compact, ultra_compact]

    def _normalize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        if not params:
            return {}

        allowed = {
            "topic",
            "search_depth",
            "max_results",
            "include_answer",
            "include_raw_content",
            "include_images",
            "include_image_descriptions",
            "days",
            "include_domains",
            "exclude_domains",
        }
        normalized: dict[str, Any] = {}
        for key, value in params.items():
            if key not in allowed and key != "time_range":
                continue
            if key == "time_range":
                days = _parse_time_range_to_days(value)
                if days is not None:
                    normalized["days"] = days
                continue
            if key in {"include_domains", "exclude_domains"}:
                domains = _normalize_domains(value if isinstance(value, list) else None)
                if domains:
                    normalized[key] = domains[:10]
                continue
            if key == "max_results":
                try:
                    normalized[key] = max(1, min(int(value), 20))
                except Exception:
                    normalized[key] = 5
                continue
            if value is None:
                continue
            normalized[key] = value
        return normalized


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
        self.last_attempt_count = 0
        self.logger = get_logger(__name__)

    def search(
        self,
        spec: SearchQuerySpec,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawArticle]:
        if not self.api_key:
            self.last_attempt_count = 0
            self.logger.warning("bocha_api_key_missing query_id=%s", spec.query_id)
            return []

        payload: dict[str, Any] = {
            "query": spec.query,
            **self.default_params,
        }
        if include_domains:
            payload["site_filter"] = include_domains
        _ = exclude_domains

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            self.last_attempt_count = 1
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


def _parse_time_range_to_days(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)\s*d", text)
    if match:
        return max(int(match.group(1)), 1)
    return None


def _normalize_domains(domains: list[str] | None) -> list[str]:
    if not domains:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        token = str(domain).strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _safe_error_body(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    text = (response.text or "").strip()
    if not text:
        return ""
    return text[:300]
