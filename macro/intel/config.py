from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import MacroThemeType
from macro.intel.models import MacroLayer, SearchQuerySpec


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_engine: dict[str, str]
    dual_search_topics: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_weight: float
    event_severity: float
    market_impact: float
    freshness: float
    cross_source_confirm: float
    transmission_chain: float


class ScoringThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high: float = 75.0
    medium: float = 55.0


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: ScoringWeights
    thresholds: ScoringThresholds


class UpgradeRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] = Field(default_factory=list)
    market_move_keywords: list[str] = Field(default_factory=list)


class DedupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_similarity_threshold: float = 0.9
    by: list[str] = Field(default_factory=list)
    time_window_hours: int | None = None


class ClusterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_window_hours: int = 48
    title_similarity_threshold: float = 0.86


class QuotasConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cn_top: int | None = None
    us_top: int | None = None
    cross_market_top: int | None = None
    max_same_topic_items: int | None = None


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = "json"
    required_fields: list[str] = Field(default_factory=list)


class LLMEditorPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[str] = Field(default_factory=list)


class MacroIntelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layers: dict[str, list[dict]]
    routing: RoutingConfig
    sources: dict[str, dict[str, float]]
    engines: dict[str, dict]
    scoring: ScoringConfig
    upgrade_rules: UpgradeRulesConfig
    dedup: DedupConfig
    cluster: ClusterConfig
    quotas: QuotasConfig = Field(default_factory=QuotasConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    llm_editor_policy: LLMEditorPolicyConfig = Field(default_factory=LLMEditorPolicyConfig)

    def build_query_specs(self) -> list[SearchQuerySpec]:
        specs: list[SearchQuerySpec] = []
        for layer_name, rows in self.layers.items():
            layer = MacroLayer(layer_name)
            for row in rows:
                specs.append(
                    SearchQuerySpec(
                        query_id=row["query_id"],
                        topic=row["topic"],
                        layer=layer,
                        query=row["query"],
                        theme_type=MacroThemeType(row["theme_type"]),
                        language=row.get("language", "zh"),
                        region=row.get("region", "CN"),
                        source_profile=row.get("source_profile", "CN"),
                        route=row.get("route"),
                        tavily_profile=row.get("tavily_profile"),
                    )
                )
        return specs


_DEFAULT_SCORING_WEIGHTS = {
    "source_weight": 0.20,
    "event_severity": 0.20,
    "market_impact": 0.20,
    "freshness": 0.15,
    "cross_source_confirm": 0.15,
    "transmission_chain": 0.10,
}

_DEFAULT_UPGRADE_KEYWORDS = [
    "能源",
    "油价",
    "航道",
    "制裁",
    "关税",
    "出口管制",
    "流动性",
    "主权融资",
    "汇率",
    "地缘",
]

_DEFAULT_MARKET_MOVE_KEYWORDS = [
    "oil",
    "treasury yield",
    "dollar",
    "gold",
    "volatility",
    "美债",
    "美元",
    "黄金",
]

_POLICY_CATEGORIES = {
    "monetary_policy",
    "fiscal_policy",
    "financial_regulation",
}

_DOMESTIC_AGGREGATE_CATEGORIES = {
    "growth_inflation",
    "inflation",
    "labor",
    "growth",
    "property",
}

_MARKET_MOVE_HINTS = {
    "oil",
    "gas",
    "lng",
    "yield",
    "dollar",
    "gold",
    "fx",
    "cny",
    "dxy",
    "volatility",
    "美元",
    "美债",
    "油价",
    "黄金",
    "汇率",
    "波动",
    "股市",
}


def _normalize_macro_intel_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("macro intel config must be a YAML mapping")
    # Legacy v1 schema can be validated directly.
    if "query_groups" not in raw:
        return raw
    return _convert_v1_1_to_v1(raw)


def _convert_v1_1_to_v1(raw: dict[str, Any]) -> dict[str, Any]:
    defaults = _as_dict(raw.get("defaults"))
    routing_raw = _as_dict(raw.get("routing"))
    scoring_raw = _as_dict(raw.get("scoring"))
    query_groups = _as_dict(raw.get("query_groups"))

    layers: dict[str, list[dict[str, Any]]] = {"regular": [], "sentinel": []}
    dual_topics: set[str] = set()
    topic_query_texts: dict[str, list[str]] = {}

    for group_name, group_entries in query_groups.items():
        if not isinstance(group_entries, dict):
            continue
        layer = "sentinel" if str(group_name).lower() == "sentinel" else "regular"

        for entry_key, entry in group_entries.items():
            if not isinstance(entry, dict):
                continue
            topic = str(entry.get("category") or entry_key).strip()
            if not topic:
                continue
            route = str(entry.get("route") or "").strip().lower()
            if route == "dual":
                dual_topics.add(topic.lower())

            region = str(entry.get("region") or "CN").strip() or "CN"
            source_profile = "CN" if region.upper() == "CN" else "INTL"
            theme_type = _map_theme_type(topic=topic, layer=layer)
            queries_by_lang = _as_dict(entry.get("queries"))

            for language, query_list in queries_by_lang.items():
                if not isinstance(query_list, list):
                    continue
                lang = str(language).strip().lower() or "zh"
                for idx, query in enumerate(query_list, start=1):
                    query_text = str(query).strip()
                    if not query_text:
                        continue
                    query_id = f"{layer}_{entry_key}_{lang}_{idx:02d}"
                    layers[layer].append(
                        {
                            "query_id": query_id,
                            "topic": topic,
                            "layer": layer,
                            "query": query_text,
                            "theme_type": theme_type.value,
                            "language": lang,
                            "region": region,
                            "source_profile": source_profile,
                            "route": route or None,
                            "tavily_profile": str(entry.get("tavily_profile") or "").strip().lower() or None,
                        }
                    )
                    topic_query_texts.setdefault(topic.lower(), []).append(query_text.lower())

    for category in _as_str_list(routing_raw.get("force_dual_for_categories")):
        dual_topics.add(category.lower())

    dual_keywords = _as_str_list(routing_raw.get("dual_keywords"))
    for keyword in dual_keywords:
        needle = keyword.lower()
        for topic, texts in topic_query_texts.items():
            if any(needle in text for text in texts):
                dual_topics.add(topic)

    default_routing = _as_dict(routing_raw.get("default"))
    routing = {
        "default_engine": {
            "zh_cn": str(default_routing.get("zh") or "bocha").lower(),
            "en_or_global": str(default_routing.get("en") or "tavily").lower(),
        },
        "dual_search_topics": sorted(dual_topics),
    }

    sources = _build_source_weights(raw=raw, scoring_raw=scoring_raw)
    engines = _build_engine_defaults(raw=raw, defaults=defaults)
    scoring = _build_scoring_thresholds(scoring_raw=scoring_raw)
    upgrade_rules = _build_upgrade_rules(raw=raw)

    cluster_enabled = True
    post_processing = _as_dict(raw.get("post_processing"))
    clustering_cfg = _as_dict(post_processing.get("clustering"))
    if "enabled" in clustering_cfg:
        cluster_enabled = bool(clustering_cfg.get("enabled"))

    cluster_window = int(_safe_float(defaults.get("dedup_window_hours"), 48))
    cluster_similarity = 0.86 if cluster_enabled else 1.0
    dedup_cfg = _as_dict(post_processing.get("dedup"))
    dedup_by = [x.strip().lower() for x in _as_str_list(dedup_cfg.get("by")) if x.strip()]
    dedup_time_window = int(_safe_float(defaults.get("dedup_window_hours"), 72))
    dedup_time_window_out: int | None = dedup_time_window if "time_window" in dedup_by else None
    quotas_raw = _as_dict(raw.get("quotas"))
    quotas = {
        "cn_top": _safe_int_or_none(quotas_raw.get("cn_top")),
        "us_top": _safe_int_or_none(quotas_raw.get("us_top")),
        "cross_market_top": _safe_int_or_none(quotas_raw.get("cross_market_top")),
        "max_same_topic_items": _safe_int_or_none(quotas_raw.get("max_same_topic_items")),
    }
    output_raw = _as_dict(raw.get("output"))
    output = {
        "format": str(output_raw.get("format") or "json"),
        "required_fields": _as_str_list(output_raw.get("required_fields")),
    }
    llm_editor_policy_raw = _as_dict(raw.get("llm_editor_policy"))
    llm_editor_policy = {
        "rules": _as_str_list(llm_editor_policy_raw.get("rules")),
    }

    return {
        "layers": layers,
        "routing": routing,
        "sources": sources,
        "engines": engines,
        "scoring": scoring,
        "upgrade_rules": upgrade_rules,
        "dedup": {
            "title_similarity_threshold": 0.90,
            "by": dedup_by,
            "time_window_hours": dedup_time_window_out,
        },
        "cluster": {
            "time_window_hours": max(cluster_window, 1),
            "title_similarity_threshold": cluster_similarity,
        },
        "quotas": quotas,
        "output": output,
        "llm_editor_policy": llm_editor_policy,
    }


def _map_theme_type(*, topic: str, layer: str) -> MacroThemeType:
    normalized = topic.strip().lower()
    if normalized in _POLICY_CATEGORIES:
        return MacroThemeType.POLICY_ENVIRONMENT
    if normalized in _DOMESTIC_AGGREGATE_CATEGORIES:
        return MacroThemeType.DOMESTIC_AGGREGATE
    if layer == "sentinel":
        return MacroThemeType.OVERSEAS_MAPPING
    if normalized in {"fx", "commodities", "trade_fx", "fiscal_rates", "banking_credit"}:
        return MacroThemeType.OVERSEAS_MAPPING
    return MacroThemeType.OVERSEAS_MAPPING


def _build_source_weights(*, raw: dict[str, Any], scoring_raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    source_weight_cfg = _as_dict(scoring_raw.get("source_weight"))
    official_score = _safe_float(source_weight_cfg.get("official"), 25.0)
    media_score = _safe_float(
        source_weight_cfg.get("tier1_media"),
        _safe_float(source_weight_cfg.get("mainstream_media"), 20.0),
    )
    max_score = max(official_score, media_score, 1.0)
    official_weight = round(min(max(official_score / max_score, 0.0), 1.0), 3)
    media_weight = round(min(max(media_score / max_score, 0.0), 1.0), 3)

    sources_raw = _as_dict(raw.get("sources"))
    cn_raw = _as_dict(sources_raw.get("cn"))
    intl_raw = _as_dict(sources_raw.get("us_global"))

    cn = _weight_profile_sources(cn_raw, official_weight=official_weight, media_weight=media_weight)
    intl = _weight_profile_sources(intl_raw, official_weight=official_weight, media_weight=media_weight)

    if not cn:
        cn = {"gov.cn": 0.98, "pbc.gov.cn": 0.98, "stats.gov.cn": 0.96}
    if not intl:
        intl = {"federalreserve.gov": 0.98, "treasury.gov": 0.98, "reuters.com": 0.82}

    return {"CN": cn, "INTL": intl}


def _weight_profile_sources(
    profile: dict[str, Any],
    *,
    official_weight: float,
    media_weight: float,
) -> dict[str, float]:
    weighted: dict[str, float] = {}
    for domain in _as_str_list(profile.get("official_domains")):
        normalized = _normalize_domain(domain)
        if normalized:
            weighted[normalized] = max(weighted.get(normalized, 0.0), official_weight)
    for domain in _as_str_list(profile.get("media_domains")):
        normalized = _normalize_domain(domain)
        if normalized:
            weighted[normalized] = max(weighted.get(normalized, 0.0), media_weight)
    return weighted


def _build_engine_defaults(*, raw: dict[str, Any], defaults: dict[str, Any]) -> dict[str, dict[str, Any]]:
    engines_raw = _as_dict(raw.get("engines"))
    tavily_raw = _as_dict(engines_raw.get("tavily"))
    bocha_raw = _as_dict(engines_raw.get("bocha"))

    max_results = int(_safe_float(defaults.get("max_results_per_query"), 8))
    lookback_days = int(_safe_float(defaults.get("lookback_days"), 3))

    tavily_default = _as_dict(tavily_raw.get("search_defaults"))
    if not tavily_default:
        tavily_default = {
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": True,
        }
    if "max_results" not in tavily_default:
        tavily_default["max_results"] = max_results
    if "time_range" not in tavily_default:
        tavily_default["time_range"] = f"{lookback_days}d"

    tavily_finance = _as_dict(tavily_raw.get("finance_defaults"))
    if not tavily_finance:
        tavily_finance = dict(tavily_default)

    tavily = {
        "default_params": tavily_default,
        "profiles": {
            "news": dict(tavily_default),
            "finance": tavily_finance,
        },
    }

    bocha = _as_dict(bocha_raw.get("search_defaults"))
    if "count" not in bocha:
        bocha["count"] = max_results
    if "freshness" not in bocha and "freshness_days" not in bocha:
        bocha["freshness_days"] = lookback_days
    if not bocha:
        bocha = {"count": max_results, "freshness_days": lookback_days}

    return {"tavily": tavily, "bocha": bocha}


def _build_scoring_thresholds(*, scoring_raw: dict[str, Any]) -> dict[str, Any]:
    thresholds_raw = _as_dict(scoring_raw.get("thresholds"))
    high = _safe_float(thresholds_raw.get("headline_candidate"), 75.0)
    medium = _safe_float(thresholds_raw.get("brief_candidate"), 55.0)
    return {"weights": _DEFAULT_SCORING_WEIGHTS, "thresholds": {"high": high, "medium": medium}}


def _build_upgrade_rules(*, raw: dict[str, Any]) -> dict[str, list[str]]:
    keywords: list[str] = []
    market_move_keywords: list[str] = []

    for token in _DEFAULT_UPGRADE_KEYWORDS:
        _append_unique(keywords, token)
    for token in _DEFAULT_MARKET_MOVE_KEYWORDS:
        _append_unique(market_move_keywords, token)

    routing_raw = _as_dict(raw.get("routing"))
    for token in _as_str_list(routing_raw.get("dual_keywords")):
        if _is_market_move_token(token):
            _append_unique(market_move_keywords, token)
        else:
            _append_unique(keywords, token)

    triggers_raw = _as_dict(raw.get("triggers"))
    for sentence in _as_str_list(triggers_raw.get("promote_to_macro_candidate_if_any_two")):
        for token in _extract_keywords(sentence):
            if _is_market_move_token(token):
                _append_unique(market_move_keywords, token)
            else:
                _append_unique(keywords, token)

    return {"keywords": keywords, "market_move_keywords": market_move_keywords}


def _extract_keywords(text: str) -> list[str]:
    if not text:
        return []

    cleaned = (
        text.replace("涉及", " ")
        .replace("已引发", " ")
        .replace("可能改变", " ")
        .replace("明显", " ")
        .replace("波动", " ")
        .replace("或", " ")
        .replace("和", " ")
        .replace("与", " ")
    )
    normalized = re.sub(r"[、,，。；;:：/()（）]|\bor\b|\band\b", " ", cleaned, flags=re.IGNORECASE)
    tokens: list[str] = []
    for chunk in normalized.split():
        term = chunk.strip().strip('"').strip("'")
        if len(term) < 2:
            continue
        if term in {"全球市场", "市场", "预期", "降息预期"}:
            continue
        _append_unique(tokens, term)
    return tokens


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")


def _is_market_move_token(token: str) -> bool:
    lowered = token.lower()
    return any(hint in lowered for hint in _MARKET_MOVE_HINTS)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _append_unique(items: list[str], value: str) -> None:
    text = value.strip()
    if not text:
        return
    if text not in items:
        items.append(text)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int_or_none(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def load_macro_intel_config(path: str | Path) -> MacroIntelConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    normalized = _normalize_macro_intel_config(raw)
    return MacroIntelConfig.model_validate(normalized)
