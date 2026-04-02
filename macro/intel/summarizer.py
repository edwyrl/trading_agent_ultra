from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from macro.intel.editor import _normalize_text, complete_with_role
from macro.intel.models import RawArticle, ScoredEvent
from shared.config import settings
from shared.llm.registry import LLMRegistry
from shared.llm.router import LLMRouter
from shared.logging import get_logger


class MacroSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    what_happened: str
    why_it_matters: str
    market_impact: str
    key_numbers: list[str] = Field(default_factory=list)
    policy_signal: str = ""
    confidence: str = "medium"


class MacroNewsSummarizer:
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
    def from_settings(cls) -> "MacroNewsSummarizer | None":
        try:
            router = LLMRouter(registry=LLMRegistry.from_yaml(settings.llm.models_config_path))
            router.resolve(role=settings.macro_intel.summarizer_role)
        except Exception as exc:
            get_logger(__name__).warning(
                "macro_summarizer_role_invalid role=%s err=%s",
                settings.macro_intel.summarizer_role,
                exc,
            )
            return None
        return cls(
            role=settings.macro_intel.summarizer_role,
            router=router,
            timeout_seconds=settings.macro_intel.summarizer_timeout_seconds,
        )

    def summarize(self, *, scored: ScoredEvent, region: str, category: str) -> MacroSummaryResult:
        prompt = self._build_prompt(scored=scored, region=region, category=category)
        text = complete_with_role(
            router=self.router,
            role=self.role,
            user_prompt=prompt,
            timeout_seconds=self.timeout_seconds,
            logger=self.logger,
        )
        parsed = _parse_summary_json(text) if text else None
        if parsed is not None:
            return parsed
        return self._fallback(scored=scored, region=region, category=category)

    def _build_prompt(self, *, scored: ScoredEvent, region: str, category: str) -> str:
        evidence = _build_evidence(scored.cluster.articles)
        return (
            "你将收到多条宏观新闻证据，请做事件级整合并输出 JSON。"
            "严格只输出 JSON 对象，不要额外解释。\n"
            "字段要求："
            '{"summary":"", "what_happened":"", "why_it_matters":"", "market_impact":"", '
            '"key_numbers":[], "policy_signal":"", "confidence":"high|medium|low"}\n'
            "约束：summary<=120字；why_it_matters<=80字；必须引用输入证据，不可编造。\n"
            f"region={region}\n"
            f"category={category}\n"
            f"score={scored.score:.2f}\n"
            f"labels={','.join(scored.labels[:6]) if scored.labels else 'none'}\n"
            f"evidence:\n{evidence}\n"
        )

    def _fallback(self, *, scored: ScoredEvent, region: str, category: str) -> MacroSummaryResult:
        top = scored.cluster.articles[0]
        key_numbers = _extract_key_numbers(scored.cluster.articles)
        market_impact = _derive_market_impact(scored.cluster.combined_text)
        key_fact = _pick_fact_sentence(scored.cluster.articles)
        what_happened = _normalize_text(top.title)
        why_it_matters = (
            f"{region}的{category}事件可能通过{market_impact}链条改变政策与资产定价预期。"
        )
        summary = _normalize_text(
            f"{what_happened}；{key_fact or '事件出现增量变化'}；{why_it_matters}"
        )
        policy_signal = _derive_policy_signal(scored.cluster.combined_text)
        confidence = "high" if scored.score >= 80 else "medium" if scored.score >= 65 else "low"
        return MacroSummaryResult(
            summary=summary,
            what_happened=what_happened,
            why_it_matters=_normalize_text(why_it_matters),
            market_impact=market_impact,
            key_numbers=key_numbers,
            policy_signal=policy_signal,
            confidence=confidence,
        )


def _build_evidence(articles: list[RawArticle]) -> str:
    rows: list[str] = []
    for idx, article in enumerate(articles[:4], start=1):
        content = " ".join((article.content or "").split())
        snippet = content[:280]
        published = article.published_at.isoformat() if article.published_at else "unknown"
        rows.append(
            f"[{idx}] title={article.title}\n"
            f"domain={article.domain}; published_at={published}\n"
            f"content={snippet}\n"
        )
    return "\n".join(rows)


def _parse_summary_json(text: str) -> MacroSummaryResult | None:
    if not text:
        return None
    normalized = text.strip()
    parsed = _load_json_obj(normalized)
    if parsed is None:
        match = re.search(r"\{.*\}", normalized, flags=re.DOTALL)
        if match:
            parsed = _load_json_obj(match.group(0))
    if not isinstance(parsed, dict):
        return None
    try:
        data = MacroSummaryResult.model_validate(parsed)
    except Exception:
        return None
    data.summary = _normalize_text(data.summary)
    data.what_happened = _normalize_text(data.what_happened)
    data.why_it_matters = _normalize_text(data.why_it_matters)
    data.market_impact = _normalize_text(data.market_impact)
    data.policy_signal = _normalize_text(data.policy_signal)
    data.key_numbers = [x for x in (_normalize_text(x) for x in data.key_numbers) if x]
    return data


def _load_json_obj(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _pick_fact_sentence(articles: list[RawArticle]) -> str:
    for article in articles[:4]:
        content = " ".join((article.content or "").split())
        if not content:
            continue
        if len(content) > 120:
            return _normalize_text(content[:120] + "…")
        return _normalize_text(content)
    return ""


def _extract_key_numbers(articles: list[RawArticle]) -> list[str]:
    pattern = r"\d+(?:\.\d+)?\s?(?:%|bp|bps|亿|万亿|trillion|billion|million|mn)"
    values: list[str] = []
    for article in articles[:4]:
        text = f"{article.title} {article.content or ''}"
        for token in re.findall(pattern, text, flags=re.IGNORECASE):
            normalized = " ".join(token.lower().split())
            if normalized not in values:
                values.append(normalized)
            if len(values) >= 5:
                return values
    return values


def _derive_market_impact(text: str) -> str:
    lowered = text.lower()
    impacts: list[str] = []
    if any(k in lowered for k in ["yield", "利率", "treasury"]):
        impacts.append("利率")
    if any(k in lowered for k in ["dollar", "fx", "汇率", "美元"]):
        impacts.append("汇率")
    if any(k in lowered for k in ["oil", "gold", "天然气", "油价", "黄金"]):
        impacts.append("大宗商品")
    if any(k in lowered for k in ["volatility", "risk appetite", "波动", "风险偏好"]):
        impacts.append("风险偏好")
    if not impacts:
        impacts.append("政策预期")
    return "/".join(dict.fromkeys(impacts))


def _derive_policy_signal(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["降息", "rate cut", "宽松", "liquidity injection"]):
        return "偏宽松"
    if any(k in lowered for k in ["加息", "rate hike", "收紧", "tightening"]):
        return "偏收紧"
    if any(k in lowered for k in ["维持", "steady", "unchanged"]):
        return "中性维持"
    return "待观察"
