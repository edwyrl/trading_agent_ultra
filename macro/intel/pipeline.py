from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime

from contracts.enums import MacroBiasTag, SourceType
from macro.intel.clients import BochaSearchClient, SearchClient, TavilySearchClient
from macro.intel.clustering import EventClusterer
from macro.intel.config import MacroIntelConfig, load_macro_intel_config
from macro.intel.dedup import DocumentDeduplicator
from macro.intel.models import RawArticle, ScoredEvent, SearchEngine, SearchQuerySpec
from macro.intel.router import MacroQueryRouter
from macro.intel.scoring import EventScorer
from macro.retriever import MacroEvent
from shared.config import settings
from shared.logging import get_logger


class MacroIntelPipeline:
    def __init__(
        self,
        *,
        config: MacroIntelConfig,
        clients: dict[SearchEngine, SearchClient],
    ):
        self.config = config
        self.clients = clients
        self.router = MacroQueryRouter(config.routing)
        self.dedup = DocumentDeduplicator(title_similarity_threshold=config.dedup.title_similarity_threshold)
        self.clusterer = EventClusterer(
            time_window_hours=config.cluster.time_window_hours,
            title_similarity_threshold=config.cluster.title_similarity_threshold,
        )
        self.scorer = EventScorer(config)
        self.logger = get_logger(__name__)

    @classmethod
    def from_settings(cls, config_path: str | None = None) -> "MacroIntelPipeline":
        path = config_path or settings.macro_intel_config_path
        config = load_macro_intel_config(path)
        clients: dict[SearchEngine, SearchClient] = {
            SearchEngine.TAVILY: TavilySearchClient(
                api_key=settings.tavily_api_key,
                base_url=settings.tavily_base_url,
                timeout_seconds=settings.macro_intel_timeout_seconds,
                default_params=config.engines.get("tavily", {}),
            ),
            SearchEngine.BOCHA: BochaSearchClient(
                api_key=settings.bocha_api_key,
                base_url=settings.bocha_base_url,
                timeout_seconds=settings.macro_intel_timeout_seconds,
                default_params=config.engines.get("bocha", {}),
            ),
        }
        return cls(config=config, clients=clients)

    def run(self, as_of_date: date) -> list[MacroEvent]:
        specs = self.config.build_query_specs()
        articles = self._collect_articles(specs)
        deduped = self.dedup.dedup(articles)
        clusters = self.clusterer.cluster(deduped)
        scored = [self.scorer.score(c) for c in clusters]
        events = self._to_macro_events(scored=scored, as_of_date=as_of_date)
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

    def _to_macro_events(self, *, scored: list[ScoredEvent], as_of_date: date) -> list[MacroEvent]:
        thresholds = self.config.scoring.thresholds
        scored.sort(key=lambda s: s.score, reverse=True)
        events: list[MacroEvent] = []

        for idx, item in enumerate(scored, start=1):
            if not item.upgraded_to_macro_candidate and item.score < thresholds.medium:
                continue

            summary = self._build_event_summary(item)
            bias_hint = self._derive_bias_hint(item)
            top_article = item.cluster.articles[0]

            events.append(
                MacroEvent(
                    event_id=f"intel:{as_of_date:%Y%m%d}:{idx:03d}:{abs(hash(item.cluster.cluster_id))}",
                    title=item.cluster.representative_title,
                    summary=summary,
                    theme_type=item.cluster.theme_type,
                    source_type=SourceType.NEWS,
                    published_at=top_article.published_at,
                    url=top_article.url,
                    source_id=item.cluster.cluster_id,
                    provider=self._provider_label(item.cluster.articles),
                    bias_hint=bias_hint,
                )
            )

        return events

    def _build_event_summary(self, scored: ScoredEvent) -> str:
        article_count = len(scored.cluster.articles)
        domains = sorted({a.domain for a in scored.cluster.articles})
        return (
            f"{scored.cluster.representative_title} | score={scored.score:.2f} | "
            f"docs={article_count} | domains={','.join(domains[:4])} | "
            f"labels={','.join(scored.labels[:4]) if scored.labels else 'none'}"
        )

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
