from __future__ import annotations

from datetime import UTC, datetime

from contracts.enums import MacroThemeType
from macro.intel.config import MacroIntelConfig
from macro.intel.models import EventCluster, MacroLayer, RawArticle, SearchEngine, SearchQuerySpec
from macro.intel.scoring import EventScorer


def _config() -> MacroIntelConfig:
    return MacroIntelConfig.model_validate(
        {
            "layers": {"regular": [], "sentinel": []},
            "routing": {"default_engine": {"zh_cn": "bocha", "en_or_global": "tavily"}, "dual_search_topics": []},
            "sources": {
                "CN": {"pbc.gov.cn": 0.9},
                "INTL": {"reuters.com": 0.82},
            },
            "engines": {"tavily": {"max_results": 5}, "bocha": {"count": 5}},
            "scoring": {
                "weights": {
                    "source_weight": 0.2,
                    "event_severity": 0.2,
                    "market_impact": 0.2,
                    "freshness": 0.15,
                    "cross_source_confirm": 0.15,
                    "transmission_chain": 0.1,
                },
                "thresholds": {"high": 75, "medium": 55},
            },
            "upgrade_rules": {"keywords": [], "market_move_keywords": []},
            "dedup": {"title_similarity_threshold": 0.9},
            "cluster": {"time_window_hours": 48, "title_similarity_threshold": 0.86},
            "source_policy": {"deny_domains": []},
        }
    )


def _spec() -> SearchQuerySpec:
    return SearchQuerySpec(
        query_id="q1",
        topic="monetary_policy",
        layer=MacroLayer.REGULAR,
        query="中国 货币政策",
        theme_type=MacroThemeType.POLICY_ENVIRONMENT,
        language="zh",
        region="CN",
        source_profile="CN",
    )


def _cluster(url: str) -> EventCluster:
    spec = _spec()
    article = RawArticle.from_web_result(
        engine=SearchEngine.BOCHA,
        spec=spec,
        title="央行公开市场操作维持流动性",
        url=url,
        content="政策预期与流动性",
        published_at=datetime.now(UTC),
        language="zh",
    )
    return EventCluster(
        cluster_id="clu:test:1",
        topic=spec.topic,
        layer=spec.layer,
        theme_type=spec.theme_type,
        representative_title=article.title,
        articles=[article],
    )


def test_known_source_domain_has_higher_source_weight_than_unknown_domain() -> None:
    known_cluster = _cluster("https://news.pbc.gov.cn/a1")
    unknown_cluster = _cluster("https://unknown.example.com/a1")
    scorer = EventScorer(_config())

    known = scorer.score(known_cluster)
    unknown = scorer.score(unknown_cluster)

    assert known.breakdown.source_weight > unknown.breakdown.source_weight
    assert known.score > unknown.score


def test_unknown_domain_source_weight_falls_back_to_default() -> None:
    cluster = _cluster("https://unknown.example.com/a1")
    scored = EventScorer(_config()).score(cluster)
    assert scored.breakdown.source_weight == 0.5
