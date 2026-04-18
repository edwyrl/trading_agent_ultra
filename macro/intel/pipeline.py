from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from contracts.enums import MacroBiasTag, SourceType
from macro.intel.clients import BochaSearchClient, SearchClient, TavilySearchClient
from macro.intel.clustering import EventClusterer
from macro.intel.config import MacroIntelConfig, load_macro_intel_config
from macro.intel.dedup import DocumentDeduplicator
from macro.intel.editor import MacroWhyItMattersEditor
from macro.intel.models import EventCluster, RawArticle, ScoredEvent, SearchEngine, SearchQuerySpec
from macro.intel.router import MacroQueryRouter
from macro.intel.scoring import EventScorer
from macro.intel.summarizer import MacroNewsSummarizer, MacroSummaryResult
from macro.retriever import MacroEvent
from shared.config import settings
from shared.logging import get_logger


class MacroIntelPipeline:
    _EVAL_SELECTED_TARGET = 6
    _EVAL_NON_SELECTED_TARGET = 6
    _SEARCH_ENGINES = (SearchEngine.BOCHA.value, SearchEngine.TAVILY.value)

    def __init__(
        self,
        *,
        config: MacroIntelConfig,
        clients: dict[SearchEngine, SearchClient],
        event_log_path: str | None = None,
        eval_pack_path: str | None = None,
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
        self.eval_pack_path = Path(eval_pack_path) if eval_pack_path else None
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
            eval_pack_path=settings.macro_intel.eval_pack_path,
            editor=editor,
            summarizer=summarizer,
        )

    def run(self, as_of_date: date) -> list[MacroEvent]:
        specs = self.config.build_query_specs()
        articles, search_usage = self._collect_articles(specs)
        deduped = self.dedup.dedup(articles)
        clusters = self.clusterer.cluster(deduped)
        scored = [self.scorer.score(c) for c in clusters]
        events, log_rows, selected_items, rejected_items = self._to_macro_events(scored=scored, as_of_date=as_of_date)
        self._write_event_log(as_of_date=as_of_date, rows=log_rows, search_usage=search_usage)
        self._write_eval_pack(
            as_of_date=as_of_date,
            scored=scored,
            selected_items=selected_items,
            rejected_items=rejected_items,
        )
        self._log_search_usage(as_of_date=as_of_date, spec_count=len(specs), usage=search_usage)
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

    def _collect_articles(self, specs: list[SearchQuerySpec]) -> tuple[list[RawArticle], dict[str, dict[str, int]]]:
        all_rows: list[RawArticle] = []
        usage = self._init_search_usage()
        deny_domains = list(self.config.source_policy.deny_domains)
        for spec in specs:
            engines = self.router.resolve_engines(spec)
            for engine in engines:
                client = self.clients.get(engine)
                if client is None:
                    continue
                engine_key = engine.value
                usage["call_count"][engine_key] += 1
                rows = client.search(spec, include_domains=None, exclude_domains=deny_domains)
                usage["api_attempts"][engine_key] += self._client_last_attempt_count(client=client)
                usage["raw_rows"][engine_key] += len(rows)
                filtered_rows = self._filter_rows_by_deny_domains(rows=rows, deny_domains=deny_domains)
                usage["filtered_rows"][engine_key] += len(filtered_rows)
                all_rows.extend(filtered_rows)

                self.logger.info(
                    "macro_intel_query_done query_id=%s topic=%s engine=%s rows=%s filtered_rows=%s attempts=%s dual=%s",
                    spec.query_id,
                    spec.topic,
                    engine_key,
                    len(rows),
                    len(filtered_rows),
                    self._client_last_attempt_count(client=client),
                    self.router.is_dual_search(spec),
                )
        return all_rows, usage

    def _init_search_usage(self) -> dict[str, dict[str, int]]:
        return {
            "call_count": {engine: 0 for engine in self._SEARCH_ENGINES},
            "api_attempts": {engine: 0 for engine in self._SEARCH_ENGINES},
            "raw_rows": {engine: 0 for engine in self._SEARCH_ENGINES},
            "filtered_rows": {engine: 0 for engine in self._SEARCH_ENGINES},
        }

    @staticmethod
    def _client_last_attempt_count(*, client: SearchClient) -> int:
        value = getattr(client, "last_attempt_count", None)
        if isinstance(value, int) and value >= 0:
            return value
        return 1

    def _log_search_usage(self, *, as_of_date: date, spec_count: int, usage: dict[str, dict[str, int]]) -> None:
        calls = usage.get("call_count", {})
        attempts = usage.get("api_attempts", {})
        rows = usage.get("filtered_rows", {})

        self.logger.info(
            "macro_intel_search_usage as_of_date=%s specs=%s bocha_calls=%s tavily_calls=%s bocha_attempts=%s tavily_attempts=%s bocha_rows=%s tavily_rows=%s",
            as_of_date,
            spec_count,
            calls.get(SearchEngine.BOCHA.value, 0),
            calls.get(SearchEngine.TAVILY.value, 0),
            attempts.get(SearchEngine.BOCHA.value, 0),
            attempts.get(SearchEngine.TAVILY.value, 0),
            rows.get(SearchEngine.BOCHA.value, 0),
            rows.get(SearchEngine.TAVILY.value, 0),
        )

        thresholds = self.config.usage_alert
        self._warn_if_usage_exceeded(
            as_of_date=as_of_date,
            engine=SearchEngine.BOCHA.value,
            call_count=calls.get(SearchEngine.BOCHA.value, 0),
            call_warn=thresholds.bocha_call_warn,
            attempt_count=attempts.get(SearchEngine.BOCHA.value, 0),
            attempt_warn=thresholds.bocha_attempt_warn,
            spec_count=spec_count,
        )
        self._warn_if_usage_exceeded(
            as_of_date=as_of_date,
            engine=SearchEngine.TAVILY.value,
            call_count=calls.get(SearchEngine.TAVILY.value, 0),
            call_warn=thresholds.tavily_call_warn,
            attempt_count=attempts.get(SearchEngine.TAVILY.value, 0),
            attempt_warn=thresholds.tavily_attempt_warn,
            spec_count=spec_count,
        )

    def _warn_if_usage_exceeded(
        self,
        *,
        as_of_date: date,
        engine: str,
        call_count: int,
        call_warn: int,
        attempt_count: int,
        attempt_warn: int,
        spec_count: int,
    ) -> None:
        over_call = call_count > call_warn
        over_attempt = attempt_count > attempt_warn
        if not over_call and not over_attempt:
            return
        self.logger.warning(
            "macro_intel_search_usage_alert as_of_date=%s engine=%s call_count=%s call_warn=%s api_attempts=%s attempt_warn=%s spec_count=%s over_call=%s over_attempt=%s",
            as_of_date,
            engine,
            call_count,
            call_warn,
            attempt_count,
            attempt_warn,
            spec_count,
            over_call,
            over_attempt,
        )

    def _to_macro_events(
        self,
        *,
        scored: list[ScoredEvent],
        as_of_date: date,
    ) -> tuple[list[MacroEvent], list[dict[str, Any]], list[ScoredEvent], list[tuple[ScoredEvent, str]]]:
        thresholds = self.config.scoring.thresholds
        scored.sort(key=lambda s: s.score, reverse=True)
        candidates: list[ScoredEvent] = []
        rejected: list[tuple[ScoredEvent, str]] = []
        apply_quality_gate = len(scored) > 20

        for item in scored:
            candidate, reason = self._candidate_decision(
                item=item,
                thresholds=thresholds,
                apply_quality_gate=apply_quality_gate,
            )
            if not candidate:
                if reason:
                    rejected.append((item, reason))
                continue
            candidates.append(item)

        selected, quota_rejected = self._apply_quotas_with_rejections(candidates)
        rejected.extend(quota_rejected)
        events: list[MacroEvent] = []
        log_rows: list[dict[str, Any]] = []

        for item in selected:
            bias_hint = self._derive_bias_hint(item)
            top_article = item.cluster.articles[0]
            event_id = self._stable_event_id(item)
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

        return events, log_rows, selected, rejected

    def _is_event_candidate(self, *, item: ScoredEvent, thresholds, apply_quality_gate: bool) -> bool:  # noqa: ANN001
        candidate, _ = self._candidate_decision(item=item, thresholds=thresholds, apply_quality_gate=apply_quality_gate)
        return candidate

    def _candidate_decision(self, *, item: ScoredEvent, thresholds, apply_quality_gate: bool) -> tuple[bool, str | None]:  # noqa: ANN001
        if item.score >= thresholds.medium:
            return True, None
        if not item.upgraded_to_macro_candidate:
            return False, "below_threshold"
        if not apply_quality_gate:
            return True, None

        # Upgraded sentinel/keyword events still need a minimum quality floor.
        minimum_score = max(45.0, thresholds.medium - 10.0)
        if item.score < minimum_score:
            return False, "below_threshold"
        if item.score < thresholds.medium and not self._has_trusted_source(item.cluster):
            return False, "low_trust_upgraded"
        return True, None

    def _has_trusted_source(self, cluster: EventCluster) -> bool:
        for article in cluster.articles:
            if self._domain_weight(article.domain, region=article.region) >= 0.7:
                return True
        return False

    def _domain_weight(self, domain: str, *, region: str) -> float:
        profile = "CN" if region.strip().upper() == "CN" else "INTL"
        source_map = self.config.sources.get(profile, {})
        token = self._normalize_domain(domain)
        for known, weight in source_map.items():
            ref = self._normalize_domain(known)
            if token == ref or token.endswith(f".{ref}"):
                return float(weight)
        return 0.0

    def _filter_rows_by_deny_domains(self, *, rows: list[RawArticle], deny_domains: list[str]) -> list[RawArticle]:
        if not rows:
            return []
        normalized_deny = {self._normalize_domain(d) for d in deny_domains if d}
        normalized_deny.discard("")
        if not normalized_deny:
            return rows

        return [
            row
            for row in rows
            if not any(
                self._normalize_domain(row.domain) == denied or self._normalize_domain(row.domain).endswith(f".{denied}")
                for denied in normalized_deny
            )
        ]

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        return (domain or "").strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")

    def _stable_event_id(self, scored: ScoredEvent) -> str:
        cluster = scored.cluster
        topic = "_".join(cluster.topic.strip().lower().split())[:24] or "topic"
        anchor = self._event_anchor(cluster)
        digest = hashlib.sha1(anchor.encode("utf-8")).hexdigest()[:24]
        return f"intel:{topic}:{digest}"

    def _event_anchor(self, cluster: EventCluster) -> str:
        urls = [self._canonicalize_url(article.url) for article in cluster.articles if article.url]
        stable_url = min((u for u in urls if u), default="")
        if stable_url:
            return f"{cluster.topic}|{stable_url}"
        return f"{cluster.topic}|{' '.join(cluster.representative_title.strip().lower().split())}"

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        parsed = urlsplit(url.strip())
        host = parsed.netloc.lower().replace("www.", "")
        path = parsed.path or "/"
        return urlunsplit((parsed.scheme.lower() or "https", host, path, "", ""))

    def _apply_quotas(self, candidates: list[ScoredEvent]) -> list[ScoredEvent]:
        selected, _ = self._apply_quotas_with_rejections(candidates)
        return selected

    def _apply_quotas_with_rejections(self, candidates: list[ScoredEvent]) -> tuple[list[ScoredEvent], list[tuple[ScoredEvent, str]]]:
        quotas = self.config.quotas
        if not candidates:
            return [], []

        has_region_quota = any(
            x is not None for x in (quotas.cn_top, quotas.us_top, quotas.cross_market_top)
        )
        has_topic_quota = quotas.max_same_topic_items is not None
        if not has_region_quota and not has_topic_quota:
            return candidates, []

        region_counts: dict[str, int] = defaultdict(int)
        topic_counts: dict[str, int] = defaultdict(int)
        selected: list[ScoredEvent] = []
        rejected: list[tuple[ScoredEvent, str]] = []

        for item in candidates:
            top_article = item.cluster.articles[0]
            bucket = self._quota_region_bucket(top_article.region)
            region_limit = self._quota_region_limit(bucket)
            topic_key = item.cluster.topic.lower()
            topic_limit = quotas.max_same_topic_items

            if region_limit is not None and region_counts[bucket] >= region_limit:
                rejected.append((item, self._region_quota_reason(bucket)))
                continue
            if topic_limit is not None and topic_counts[topic_key] >= topic_limit:
                rejected.append((item, "quota_topic"))
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
        return selected, rejected

    @staticmethod
    def _region_quota_reason(bucket: str) -> str:
        if bucket == "CN":
            return "quota_cn"
        if bucket == "US":
            return "quota_us"
        return "quota_cross"

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

    def _write_event_log(
        self,
        *,
        as_of_date: date,
        rows: list[dict[str, Any]],
        search_usage: dict[str, dict[str, int]] | None = None,
    ) -> None:
        if self.event_log_path is None:
            return
        policy_rows = self._apply_editor_policy_to_rows(rows)
        final_rows = self._enforce_required_fields(policy_rows)
        payload = {
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "event_count": len(final_rows),
            "search_usage": search_usage or self._init_search_usage(),
            "events": final_rows,
        }
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_eval_pack(
        self,
        *,
        as_of_date: date,
        scored: list[ScoredEvent],
        selected_items: list[ScoredEvent],
        rejected_items: list[tuple[ScoredEvent, str]],
    ) -> None:
        if self.eval_pack_path is None:
            return

        payload = self._build_eval_pack(
            as_of_date=as_of_date,
            scored=scored,
            selected_items=selected_items,
            rejected_items=rejected_items,
        )
        self.eval_pack_path.parent.mkdir(parents=True, exist_ok=True)
        self.eval_pack_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_eval_pack(
        self,
        *,
        as_of_date: date,
        scored: list[ScoredEvent],
        selected_items: list[ScoredEvent],
        rejected_items: list[tuple[ScoredEvent, str]],
    ) -> dict[str, Any]:
        selected_samples = self._build_selected_eval_samples(selected_items)
        non_selected_samples = self._build_non_selected_eval_samples(
            scored=scored,
            rejected_items=rejected_items,
        )
        all_samples = selected_samples + non_selected_samples
        return {
            "as_of_date": as_of_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "targets": {
                "selected": self._EVAL_SELECTED_TARGET,
                "non_selected": self._EVAL_NON_SELECTED_TARGET,
                "total": self._EVAL_SELECTED_TARGET + self._EVAL_NON_SELECTED_TARGET,
            },
            "selected_count": len(selected_samples),
            "non_selected_count": len(non_selected_samples),
            "sample_count": len(all_samples),
            "shortage": {
                "selected": max(0, self._EVAL_SELECTED_TARGET - len(selected_samples)),
                "non_selected": max(0, self._EVAL_NON_SELECTED_TARGET - len(non_selected_samples)),
            },
            "selected_samples": selected_samples,
            "non_selected_samples": non_selected_samples,
            "samples": all_samples,
        }

    def _build_selected_eval_samples(self, selected_items: list[ScoredEvent]) -> list[dict[str, Any]]:
        picked = sorted(selected_items, key=lambda x: x.score, reverse=True)[: self._EVAL_SELECTED_TARGET]
        samples: list[dict[str, Any]] = []
        for idx, item in enumerate(picked, start=1):
            sample = self._eval_sample_from_scored(item=item, selected=True)
            sample["sample_id"] = f"sel-{idx:02d}"
            samples.append(sample)
        return samples

    def _build_non_selected_eval_samples(
        self,
        *,
        scored: list[ScoredEvent],
        rejected_items: list[tuple[ScoredEvent, str]],
    ) -> list[dict[str, Any]]:
        medium = float(self.config.scoring.thresholds.medium)
        seen_urls: set[str] = set()
        pool: list[dict[str, Any]] = []

        for item, reason in rejected_items:
            sample = self._eval_sample_from_scored(item=item, selected=False, reject_reason=reason)
            key = sample.get("url", "")
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            pool.append(
                {
                    "sample": sample,
                    "topic": item.cluster.topic.lower(),
                    "score": float(item.score),
                    "trusted": self._has_trusted_source(item.cluster),
                    "distance": abs(float(item.score) - medium),
                }
            )

        pool.sort(key=lambda x: (x["distance"], -int(x["trusted"]), -x["score"]))
        chosen: list[dict[str, Any]] = []
        chosen_topics: set[str] = set()
        used_urls: set[str] = set()

        for enforce_topic_diversity in (True, False):
            if len(chosen) >= self._EVAL_NON_SELECTED_TARGET:
                break
            for row in pool:
                sample = row["sample"]
                url = str(sample.get("url") or "")
                topic = row["topic"]
                if url and url in used_urls:
                    continue
                if enforce_topic_diversity and topic in chosen_topics:
                    continue
                chosen.append(sample)
                if url:
                    used_urls.add(url)
                chosen_topics.add(topic)
                if len(chosen) >= self._EVAL_NON_SELECTED_TARGET:
                    break

        if len(chosen) < self._EVAL_NON_SELECTED_TARGET:
            fill_pool = self._build_cluster_fill_samples(scored=scored)
            for sample in fill_pool:
                url = str(sample.get("url") or "")
                if url and url in used_urls:
                    continue
                sample["low_pool_fill"] = True
                chosen.append(sample)
                if url:
                    used_urls.add(url)
                if len(chosen) >= self._EVAL_NON_SELECTED_TARGET:
                    break

        final = chosen[: self._EVAL_NON_SELECTED_TARGET]
        for idx, sample in enumerate(final, start=1):
            sample["sample_id"] = f"rej-{idx:02d}"
        return final

    def _build_cluster_fill_samples(self, *, scored: list[ScoredEvent]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in sorted(scored, key=lambda x: x.score, reverse=True):
            event_id = self._stable_event_id(item)
            # Extra docs inside one cluster often indicate duplicate/aggregated stories.
            for article in item.cluster.articles[1:]:
                rows.append(
                    {
                        "sample_id": "",
                        "event_id": event_id,
                        "topic": item.cluster.topic,
                        "title": article.title,
                        "url": article.url,
                        "score": round(float(item.score), 2),
                        "source_domain": self._normalize_domain(article.domain),
                        "selected": False,
                        "reject_reason": "dedup_or_clustered",
                    }
                )
        return rows

    def _eval_sample_from_scored(
        self,
        *,
        item: ScoredEvent,
        selected: bool,
        reject_reason: str | None = None,
    ) -> dict[str, Any]:
        top_article = item.cluster.articles[0]
        row = {
            "sample_id": "",
            "event_id": self._stable_event_id(item),
            "topic": item.cluster.topic,
            "title": item.cluster.representative_title,
            "url": top_article.url,
            "score": round(float(item.score), 2),
            "source_domain": self._normalize_domain(top_article.domain),
            "selected": selected,
        }
        if not selected and reject_reason:
            row["reject_reason"] = reject_reason
        return row

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
