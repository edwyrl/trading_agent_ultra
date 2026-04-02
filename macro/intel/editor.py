from __future__ import annotations

from typing import Any

import httpx

from macro.intel.models import ScoredEvent
from shared.config import settings
from shared.llm.models import LLMProvider
from shared.llm.registry import LLMRegistry
from shared.llm.router import LLMRouter
from shared.logging import get_logger


class MacroWhyItMattersEditor:
    def __init__(
        self,
        *,
        role: str,
        router: LLMRouter,
        timeout_seconds: float,
    ) -> None:
        self.role = role
        self.router = router
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger(__name__)

    @classmethod
    def from_settings(cls) -> "MacroWhyItMattersEditor | None":
        try:
            router = LLMRouter(registry=LLMRegistry.from_yaml(settings.llm.models_config_path))
            # Warm up and validate role during boot.
            router.resolve(role=settings.macro_intel.editor_role)
        except Exception as exc:
            get_logger(__name__).warning("macro_editor_role_invalid role=%s err=%s", settings.macro_intel.editor_role, exc)
            return None
        return cls(
            role=settings.macro_intel.editor_role,
            router=router,
            timeout_seconds=settings.macro_intel.editor_timeout_seconds,
        )

    def generate(self, *, scored: ScoredEvent, region: str, category: str) -> str | None:
        user_prompt = self._build_user_prompt(scored=scored, region=region, category=category)
        text = complete_with_role(
            router=self.router,
            role=self.role,
            user_prompt=user_prompt,
            timeout_seconds=self.timeout_seconds,
            logger=self.logger,
        )
        if not text:
            return None

        return _normalize_text(text)

    def _build_user_prompt(self, *, scored: ScoredEvent, region: str, category: str) -> str:
        labels = ", ".join(scored.labels[:4]) if scored.labels else "none"
        domains = ", ".join(sorted({a.domain for a in scored.cluster.articles})[:4])
        return (
            "请用中文输出一句话（不超过60字），解释这条宏观事件为什么重要。"
            "仅输出句子本身，不要编号。\n"
            f"region={region}\n"
            f"category={category}\n"
            f"title={scored.cluster.representative_title}\n"
            f"score={scored.score:.2f}\n"
            f"labels={labels}\n"
            f"sources={domains}\n"
        )


def complete_with_role(
    *,
    router: LLMRouter,
    role: str,
    user_prompt: str,
    timeout_seconds: float,
    logger,
) -> str | None:
    try:
        route = router.resolve(role=role)
    except Exception as exc:
        logger.warning("macro_role_resolve_failed role=%s err=%s", role, exc)
        return None

    api_key, base_url = _provider_settings(route.model.provider)
    if not api_key or not base_url:
        logger.warning(
            "macro_role_provider_unavailable provider=%s role=%s",
            route.model.provider.value,
            role,
        )
        return None

    system_prompt = route.role_spec.system_prompt if route.role_spec else None
    try:
        if route.model.provider in {LLMProvider.OPENAI, LLMProvider.MOONSHOT, LLMProvider.SILICONFLOW}:
            return _chat_completion_openai_compatible(
                base_url=base_url,
                api_key=api_key,
                model=route.model.api_model,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                timeout_seconds=timeout_seconds,
                temperature=route.role_spec.temperature if route.role_spec else None,
                max_output_tokens=route.role_spec.max_output_tokens if route.role_spec else None,
            )
        if route.model.provider == LLMProvider.ANTHROPIC:
            return _chat_completion_anthropic(
                base_url=base_url,
                api_key=api_key,
                model=route.model.api_model,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                timeout_seconds=timeout_seconds,
                temperature=route.role_spec.temperature if route.role_spec else None,
                max_output_tokens=route.role_spec.max_output_tokens if route.role_spec else None,
            )
    except Exception as exc:
        logger.warning(
            "macro_role_call_failed provider=%s role=%s err=%s",
            route.model.provider.value,
            role,
            exc,
        )
        return None
    return None


def _provider_settings(provider: LLMProvider) -> tuple[str, str]:
    if provider == LLMProvider.OPENAI:
        return settings.llm.openai.api_key, settings.llm.openai.base_url
    if provider == LLMProvider.ANTHROPIC:
        return settings.llm.anthropic.api_key, settings.llm.anthropic.base_url
    if provider == LLMProvider.MOONSHOT:
        return settings.llm.moonshot.api_key, settings.llm.moonshot.base_url
    if provider == LLMProvider.SILICONFLOW:
        return settings.llm.siliconflow.api_key, settings.llm.siliconflow.base_url
    return "", ""


def _chat_completion_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_prompt: str,
    system_prompt: str | None,
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices", []) if isinstance(body, dict) else []
    if not choices:
        return ""
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "")
    return _extract_content_text(content)


def _chat_completion_anthropic(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_prompt: str,
    system_prompt: str | None,
    timeout_seconds: float,
    temperature: float | None,
    max_output_tokens: int | None,
) -> str:
    url = f"{base_url.rstrip('/')}/messages"
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": max_output_tokens or 256,
    }
    if system_prompt:
        payload["system"] = system_prompt
    if temperature is not None:
        payload["temperature"] = temperature

    resp = httpx.post(
        url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    body = resp.json()
    content = body.get("content", []) if isinstance(body, dict) else []
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return " ".join(parts).strip()


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                chunks.append(item)
        return " ".join(chunks).strip()
    return ""


def _normalize_text(text: str) -> str:
    normalized = " ".join((text or "").strip().split())
    if len(normalized) > 120:
        return normalized[:120].rstrip("，,.;。；") + "。"
    return normalized
