from __future__ import annotations

from datetime import UTC, datetime

from macro.intel.config import MacroIntelConfig
from macro.intel.models import EventCluster, EventScoreBreakdown, MacroLayer, ScoredEvent


class EventScorer:
    def __init__(self, config: MacroIntelConfig):
        self.config = config

    def score(self, cluster: EventCluster) -> ScoredEvent:
        breakdown = EventScoreBreakdown(
            source_weight=self._source_weight(cluster),
            event_severity=self._event_severity(cluster),
            market_impact=self._market_impact(cluster),
            freshness=self._freshness(cluster),
            cross_source_confirm=self._cross_source_confirm(cluster),
            transmission_chain=self._transmission_chain(cluster),
        )

        weights = self.config.scoring.weights
        score_0_1 = (
            breakdown.source_weight * weights.source_weight
            + breakdown.event_severity * weights.event_severity
            + breakdown.market_impact * weights.market_impact
            + breakdown.freshness * weights.freshness
            + breakdown.cross_source_confirm * weights.cross_source_confirm
            + breakdown.transmission_chain * weights.transmission_chain
        )
        score = round(max(0.0, min(score_0_1 * 100.0, 100.0)), 2)

        upgraded, labels = self._evaluate_upgrade(cluster)
        return ScoredEvent(
            cluster=cluster,
            score=score,
            breakdown=breakdown,
            upgraded_to_macro_candidate=upgraded,
            labels=labels,
        )

    def _source_weight(self, cluster: EventCluster) -> float:
        profile_key = self._source_profile_key(cluster)
        source_map = self.config.sources.get(profile_key, {})
        if not source_map:
            return 0.5

        vals: list[float] = []
        for article in cluster.articles:
            matched_weight = self._lookup_source_weight(domain=article.domain, source_map=source_map)
            if matched_weight is None:
                vals.append(0.5)
                continue
            vals.append(matched_weight)

        if not vals:
            return 0.5

        return max(0.0, min(sum(vals) / len(vals), 1.0))

    @staticmethod
    def _source_profile_key(cluster: EventCluster) -> str:
        region = (cluster.articles[0].region or "").strip().upper()
        if region == "CN":
            return "CN"
        return "INTL"

    def _lookup_source_weight(self, *, domain: str, source_map: dict[str, float]) -> float | None:
        token = self._normalize_domain(domain)
        for known, weight in source_map.items():
            ref = self._normalize_domain(known)
            if token == ref or token.endswith(f".{ref}"):
                return float(weight)
        return None

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        return (domain or "").strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")

    def _event_severity(self, cluster: EventCluster) -> float:
        text = cluster.combined_text.lower()
        base = 0.45 if cluster.layer == MacroLayer.REGULAR else 0.62
        keywords = [
            "sanction",
            "制裁",
            "关税",
            "出口管制",
            "地缘",
            "war",
            "冲突",
            "流动性",
            "主权",
            "违约",
        ]
        hits = sum(1 for k in keywords if k in text)
        return min(1.0, base + hits * 0.06)

    def _market_impact(self, cluster: EventCluster) -> float:
        text = cluster.combined_text.lower()
        keywords = ["yield", "fx", "dollar", "oil", "gold", "vix", "汇率", "利率", "油价", "黄金", "波动"]
        hits = sum(1 for k in keywords if k in text)
        return min(1.0, 0.35 + hits * 0.07)

    def _freshness(self, cluster: EventCluster) -> float:
        newest = max((a.published_at for a in cluster.articles if a.published_at is not None), default=None)
        if newest is None:
            return 0.45
        age_hours = max((datetime.now(UTC) - newest).total_seconds() / 3600.0, 0.0)
        if age_hours <= 6:
            return 1.0
        if age_hours <= 24:
            return 0.85
        if age_hours <= 48:
            return 0.65
        return 0.4

    def _cross_source_confirm(self, cluster: EventCluster) -> float:
        engines = {a.engine for a in cluster.articles}
        domains = {a.domain for a in cluster.articles}
        if len(engines) >= 2 and len(domains) >= 2:
            return 1.0
        if len(domains) >= 2:
            return 0.7
        return 0.4

    def _transmission_chain(self, cluster: EventCluster) -> float:
        text = cluster.combined_text.lower()
        chain_terms = ["rate", "yield", "fx", "inflation", "liquidity", "risk asset", "利率", "汇率", "通胀", "流动性"]
        hits = sum(1 for t in chain_terms if t in text)
        return min(1.0, 0.3 + hits * 0.1)

    def _evaluate_upgrade(self, cluster: EventCluster) -> tuple[bool, list[str]]:
        text = cluster.combined_text.lower()
        labels: list[str] = []

        for keyword in self.config.upgrade_rules.keywords:
            if keyword.lower() in text:
                labels.append(f"keyword:{keyword}")

        for keyword in self.config.upgrade_rules.market_move_keywords:
            if keyword.lower() in text:
                labels.append(f"market_move:{keyword}")

        upgraded = len(labels) > 0 or cluster.layer == MacroLayer.SENTINEL
        return upgraded, labels
