from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from contracts.enums import MacroBiasTag, SourceType
from macro.intel.clients import BochaSearchClient, SearchClient, TavilySearchClient
from macro.intel.clustering import EventClusterer
from macro.intel.config import MacroIntelConfig, load_macro_intel_config
from macro.intel.dedup import DocumentDeduplicator
from macro.intel.editor import MacroWhyItMattersEditor
from macro.intel.models import RawArticle, ScoredEvent, SearchEngine, SearchQuerySpec
from macro.intel.router import MacroQueryRouter
from macro.intel.scoring import EventScorer
from macro.intel.summarizer import MacroNewsSummarizer, MacroSummaryResult
from macro.retriever import MacroEvent
from shared.config import settings
from shared.logging import get_logger


class MacroIntelPipeline:
    def __init__(
        self,
        *,
        config: MacroIntelConfig,
        clients: dict[SearchEngine, SearchClient],
        event_log_path: str | None = None,
        editor: MacroWhyItMattersEditor | None = None,
        summarizer: MacroNewsSummarizer | None = None,
    ):
        self.config = config
        self.clients = clients
        self.router = MacroQueryRouter(config.routing)
        self.dedup = DocumentDeduplicator(
            title_similarity_threshold=config.dedup.title_similarity_threshold,
            by=config.dedup.by,
            time_window_hours=config.dedup.time_window_hours,
        )
        self.clusterer = EventClusterer(
            time_window_hours=config.cluster.time_window_hours,
            title_similarity_threshold=config.cluster.title_similarity_threshold,
        )
        self.scorer = EventScorer(config)
        self.logger = get_logger(__name__)
        self.event_log_path = Path(event_log_path) if event_log_path else None
        self.editor = editor
        self.summarizer = summarizer

    @classmethod
    def from_settings(cls, config_path: str | None = None) -> "MacroIntelPipeline":
        path = config_path or settings.macro_intel.config_path
        config = load_macro_intel_config(path)
        tavily_default, tavily_profiles = _resolve_tavily_engine_params(config.engines.get("tavily", {}))
        editor = MacroWhyItMattersEditor.from_settings()
        summarizer = MacroNewsSummarizer.from_settings()
        clients: dict[SearchEngine, SearchClient] = {
            SearchEngine.TAVILY: TavilySearchClient(
                api_key=settings.search.tavily.api_key,
                base_url=settings.search.tavily.base_url,
                timeout_seconds=settings.macro_intel.timeout_seconds,
                default_params=tavily_default,
                profile_params=tavily_profiles,
            ),
            SearchEngine.BOCHA: BochaSearchClient(
                api_key=settings.search.bocha.api_key,
                base_url=settings.search.bocha.base_url,
                timeout_seconds=settings.macro_intel.timeout_seconds,
                default_params=config.engines.get("bocha", {}),
            ),
        }
        return cls(
            config=config,
            clients=clients,
            event_log_path=settings.macro_intel.event_log_path,
            editor=editor,
            summarizer=summarizer,
        )

    def run(self, as_of_date: date) -> list[MacroEvent]:
        specs = self.config.build_query_specs()
        articles = self._collect_articles(specs)
        deduped = self.dedup.dedup(articles)
        clusters = self.clusterer.cluster(deduped)
        scored = [self.scorer.score(c) for c in clusters]
        events, log_rows = self._to_macro_events(scored=scored, as_of_date=as_of_date)
        self._write_event_log(as_of_date=as_of_date, rows=log_rows)
        self.logger.info(
            "macro_intel_pipeline_done as_of_date=%s specs=%s raw_articles=%s deduped=%s clusters=%s events=%s",
            as_of_date,
            len(specs),
            len(articles),
            len(deduped),
            len(clusters),
            len(events),
        )
        return events

    def _collect_articles(self, specs: list[SearchQuerySpec]) -> list[RawArticle]:
        all_rows: list[RawArticle] = []
        for spec in specs:
            engines = self.router.resolve_engines(spec)
            include_domains = list(self.config.sources.get(spec.source_profile, {}).keys())
            for engine in engines:
                client = self.clients.get(engine)
                if client is None:
                    continue
                rows = client.search(spec, include_domains=include_domains)
                all_rows.extend(rows)

                self.logger.info(
                    "macro_intel_query_done query_id=%s topic=%s engine=%s rows=%s dual=%s",
                    spec.query_id,
                    spec.topic,
                    engine.value,
                    len(rows),
                    self.router.is_dual_search(spec),
                )
        return all_rows

    def _to_macro_events(self, *, scored: list[ScoredEvent], as_of_date: date) -> tuple[list[MacroEvent], list[dict[str, Any]]]:
        thresholds = self.config.scoring.thresholds
        scored.sort(key=lambda s: s.score, reverse=True)
        candidates: list[ScoredEvent] = []

        for item in scored:
            if not item.upgraded_to_macro_candidate and item.score < thresholds.medium:
                continue
            candidates.append(item)

        selected = self._apply_quotas(candidates)
        events: list[MacroEvent] = []
        log_rows: list[dict[str, Any]] = []

        for idx, item in enumerate(selected, start=1):
            bias_hint = self._derive_bias_hint(item)
            top_article = item.cluster.articles[0]
            event_id = f"intel:{as_of_date:%Y%m%d}:{idx:03d}:{abs(hash(item.cluster.cluster_id))}"
            region = top_article.region
            category = item.cluster.topic
            summary_result = self._summarize_event(scored=item, region=region, category=category)

            events.append(
                MacroEvent(
                    event_id=event_id,
                    title=item.cluster.representative_title,
                    summary=summary_result.summary,
                    theme_type=item.cluster.theme_type,
                    source_type=SourceType.NEWS,
                    published_at=top_article.published_at,
                    url=top_article.url,
                    source_id=item.cluster.cluster_id,
                    provider=self._provider_label(item.cluster.articles),
                    bias_hint=bias_hint,
                )
            )
            log_rows.append(
                self._build_log_row(
                    event_id=event_id,
                    scored=item,
                    region=region,
                    category=category,
                    summary_result=summary_result,
                )
            )

        return events, log_rows

    def _apply_quotas(self, candidates: list[ScoredEvent]) -> list[ScoredEvent]:
        quotas = self.config.quotas
        if not candidates:
            return []

        has_region_quota = any(
            x is not None for x in (quotas.cn_top, quotas.us_top, quotas.cross_market_top)
        )
        has_topic_quota = quotas.max_same_topic_items is not None
        if not has_region_quota and not has_topic_quota:
            return candidates

        region_counts: dict[str, int] = defaultdict(int)
        topic_counts: dict[str, int] = defaultdict(int)
        selected: list[ScoredEvent] = []

        for item in candidates:
            top_article = item.cluster.articles[0]
            bucket = self._quota_region_bucket(top_article.region)
            region_limit = self._quota_region_limit(bucket)
            topic_key = item.cluster.topic.lower()
            topic_limit = quotas.max_same_topic_items

            if region_limit is not None and region_counts[bucket] >= region_limit:
                continue
            if topic_limit is not None and topic_counts[topic_key] >= topic_limit:
                continue

            selected.append(item)
            region_counts[bucket] += 1
            topic_counts[topic_key] += 1

        self.logger.info(
            "macro_intel_quotas_applied candidates=%s selected=%s cn=%s us=%s cross=%s max_same_topic=%s",
            len(candidates),
            len(selected),
            quotas.cn_top,
            quotas.us_top,
            quotas.cross_market_top,
            quotas.max_same_topic_items,
        )
        return selected

    def _quota_region_bucket(self, region: str) -> str:
        key = region.strip().upper()
        if key == "CN":
            return "CN"
        if key == "US":
            return "US"
        return "CROSS"

    def _quota_region_limit(self, bucket: str) -> int | None:
        quotas = self.config.quotas
        if bucket == "CN":
            return quotas.cn_top
        if bucket == "US":
            return quotas.us_top
        return quotas.cross_market_top

    def _build_event_summary(self, scored: ScoredEvent) -> str:
        article_count = len(scored.cluster.articles)
        domains = sorted({a.domain for a in scored.cluster.articles})
        return (
            f"{scored.cluster.representative_title} | score={scored.score:.2f} | "
            f"docs={article_count} | domains={','.join(domains[:4])} | "
            f"labels={','.join(scored.labels[:4]) if scored.labels else 'none'}"
        )

    def _summarize_event(self, *, scored: ScoredEvent, region: str, category: str) -> MacroSummaryResult:
        if self.summarizer is not None:
            result = self.summarizer.summarize(scored=scored, region=region, category=category)
        else:
            result = self._fallback_summary_result(scored=scored, region=region, category=category)

        # Keep backward compatibility: if summarizer output lacks why_it_matters, fill via editor/fallback.
        if not result.why_it_matters:
            result.why_it_matters = self._build_why_it_matters(scored=scored, region=region, category=category)
        if not result.summary:
            result.summary = self._build_event_summary(scored)
        return result

    def _provider_label(self, articles: list[RawArticle]) -> str:
        by_engine = defaultdict(int)
        for article in articles:
            by_engine[article.engine.value] += 1
        parts = [f"{k}:{v}" for k, v in sorted(by_engine.items())]
        return f"macro-intel[{';'.join(parts)}]"

    def _derive_bias_hint(self, scored: ScoredEvent) -> MacroBiasTag | None:
        text = scored.cluster.combined_text.lower()
        if "liquidity" in text or "流动性" in text:
            return MacroBiasTag.LIQUIDITY_DOMINANT
        if "policy" in text or "政策" in text:
            return MacroBiasTag.POLICY_EXPECTATION_DOMINANT
        if any(k in text for k in ["risk appetite", "风险偏好", "theme", "主题"]):
            return MacroBiasTag.RISK_APPETITE_RECOVERY
        if any(k in text for k in ["sanction", "制裁", "export control", "地缘", "关税"]):
            return MacroBiasTag.EXTERNAL_DISTURBANCE_DOMINANT
        if any(k in text for k in ["cyclical", "顺周期"]):
            return MacroBiasTag.PRO_CYCLICAL_TRADING_WARMING
        if scored.score >= self.config.scoring.thresholds.high:
            return MacroBiasTag.FUNDAMENTAL_VALIDATION_DOMINANT
        return None

    def _build_why_it_matters(self, *, scored: ScoredEvent, region: str, category: str) -> str:
        if self.editor is not None:
            generated = self.editor.generate(scored=scored, region=region, category=category)
            if generated:
                return generated
        return self._fallback_why_it_matters(scored=scored, region=region, category=category)

    def _fallback_why_it_matters(self, *, scored: ScoredEvent, region: str, category: str) -> str:
        if scored.labels:
            lead = scored.labels[0].split(":", 1)[-1]
            return f"{region}的{category}事件触发“{lead}”信号，可能通过利率、汇率与风险偏好传导至市场。"
        if scored.score >= self.config.scoring.thresholds.high:
            return f"{region}的{category}事件强度较高，可能影响政策预期与跨资产定价。"
        return f"{region}的{category}出现增量变化，需跟踪其对流动性与风险资产的边际影响。"

    def _write_event_log(self, *, as_of_date: date, rows: list[dict[str, Any]]) -> None:
        if self.event_log_path is None:
            return
        policy_rows = self._apply_editor_policy_to_rows(rows)
        final_rows = self._enforce_required_fields(policy_rows)
        payload = {
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "event_count": len(final_rows),
            "events": final_rows,
        }
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_log_row(
        self,
        *,
        event_id: str,
        scored: ScoredEvent,
        region: str,
        category: str,
        summary_result: MacroSummaryResult,
    ) -> dict[str, Any]:
        top_article = scored.cluster.articles[0]
        source_domains = sorted({a.domain for a in scored.cluster.articles})
        return {
            "event_id": event_id,
            "title": scored.cluster.representative_title,
            "region": region,
            "category": category,
            "summary": summary_result.summary,
            "what_happened": summary_result.what_happened,
            "why_it_matters": summary_result.why_it_matters,
            "market_impact": summary_result.market_impact,
            "key_numbers": summary_result.key_numbers,
            "policy_signal": summary_result.policy_signal,
            "confidence": summary_result.confidence,
            "score": round(scored.score, 2),
            "sources": source_domains,
            "published_at": top_article.published_at.isoformat() if top_article.published_at else None,
            "labels": scored.labels,
        }

    def _fallback_summary_result(self, *, scored: ScoredEvent, region: str, category: str) -> MacroSummaryResult:
        why_it_matters = self._build_why_it_matters(scored=scored, region=region, category=category)
        return MacroSummaryResult(
            summary=self._build_event_summary(scored),
            what_happened=scored.cluster.representative_title,
            why_it_matters=why_it_matters,
            market_impact=self._derive_market_impact(scored),
            key_numbers=[],
            policy_signal="待观察",
            confidence="medium",
        )

    def _derive_market_impact(self, scored: ScoredEvent) -> str:
        text = scored.cluster.combined_text.lower()
        impacts: list[str] = []
        if any(k in text for k in ["yield", "利率", "treasury"]):
            impacts.append("利率")
        if any(k in text for k in ["dollar", "fx", "汇率", "美元"]):
            impacts.append("汇率")
        if any(k in text for k in ["oil", "gold", "天然气", "油价", "黄金"]):
            impacts.append("大宗商品")
        if any(k in text for k in ["volatility", "risk appetite", "波动", "风险偏好"]):
            impacts.append("风险偏好")
        if not impacts:
            impacts.append("政策预期")
        return f"主要影响：{'/'.join(dict.fromkeys(impacts))}"

    def _apply_editor_policy_to_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rules = self.config.llm_editor_policy.rules
        if not rows:
            return []
        out = list(rows)
        rules_text = " ".join(rules)

        if "72小时" in rules_text:
            now = datetime.now(UTC)
            kept: list[dict[str, Any]] = []
            for row in out:
                published_at = row.get("published_at")
                if not isinstance(published_at, str) or not published_at:
                    kept.append(row)
                    continue
                try:
                    ts = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                except ValueError:
                    kept.append(row)
                    continue
                age_hours = (now - ts).total_seconds() / 3600.0
                if age_hours <= 72:
                    kept.append(row)
            out = kept

        if any(x in rules_text for x in ["忽略", "评论", "传闻", "rumor"]):
            out = [row for row in out if not self._is_low_quality_row(row)]

        if any(x in rules_text for x in ["优先级", "官方政策", "核心数据"]):
            out = sorted(out, key=lambda r: (self._policy_rank(r), -float(r.get("score", 0.0))))
        else:
            out = sorted(out, key=lambda r: -float(r.get("score", 0.0)))

        # Light merge safety: avoid duplicate titles occupying multiple slots.
        merged: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        for row in out:
            title = " ".join(str(row.get("title", "")).lower().split())
            if title and title in seen_titles:
                continue
            if title:
                seen_titles.add(title)
            merged.append(row)
        return merged

    def _enforce_required_fields(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        required = self.config.output.required_fields
        if not required:
            return rows

        enforced: list[dict[str, Any]] = []
        for row in rows:
            out = dict(row)
            for key in required:
                if key not in out or out[key] is None:
                    out[key] = self._default_value_for_field(key)
            enforced.append(out)
        return enforced

    @staticmethod
    def _default_value_for_field(field: str) -> Any:
        if field in {"sources"}:
            return []
        if field in {"score"}:
            return 0.0
        return ""

    @staticmethod
    def _is_low_quality_row(row: dict[str, Any]) -> bool:
        text = f"{row.get('title', '')} {row.get('what_happened', '')}".lower()
        if any(k in text for k in ["传闻", "rumor", "猜测", "opinion", "评论"]) and float(row.get("score", 0.0)) < 75:
            return True
        return False

    @staticmethod
    def _policy_rank(row: dict[str, Any]) -> int:
        text = f"{row.get('title', '')} {row.get('what_happened', '')}".lower()
        if any(k in text for k in ["政策", "降息", "加息", "fomc", "mlf", "lpr"]):
            return 0
        if any(k in text for k in ["cpi", "ppi", "pmi", "payroll", "失业率", "通胀", "就业"]):
            return 1
        if any(k in text for k in ["声明", "讲话", "guidance", "statement"]):
            return 2
        if any(k in text for k in ["利率", "汇率", "信用", "yield", "fx", "spread"]):
            return 3
        return 4


def _resolve_tavily_engine_params(config: dict) -> tuple[dict, dict[str, dict]]:
    default_params = config.get("default_params")
    if isinstance(default_params, dict):
        profiles_raw = config.get("profiles")
        profiles: dict[str, dict] = {}
        if isinstance(profiles_raw, dict):
            for key, value in profiles_raw.items():
                if isinstance(value, dict):
                    profiles[str(key).strip().lower()] = value
        return default_params, profiles
    # Legacy format: the entire object is the default payload.
    return config, {}
