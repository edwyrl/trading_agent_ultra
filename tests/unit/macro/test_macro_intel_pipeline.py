from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.enums import MacroThemeType
from macro.intel.config import MacroIntelConfig
from macro.intel.models import RawArticle, SearchEngine, SearchQuerySpec
from macro.intel.pipeline import MacroIntelPipeline
from macro.intel.router import MacroQueryRouter


class FakeClient:
    def __init__(self, engine: SearchEngine, rows: list[dict]):
        self.engine = engine
        self.rows = rows

    def search(self, spec: SearchQuerySpec, *, include_domains: list[str] | None = None) -> list[RawArticle]:
        _ = include_domains
        out: list[RawArticle] = []
        for row in self.rows:
            out.append(
                RawArticle.from_web_result(
                    engine=self.engine,
                    spec=spec,
                    title=row["title"],
                    url=row["url"],
                    content=row.get("content", ""),
                    published_at=row.get("published_at"),
                    language=spec.language,
                    source_name=row.get("source_name"),
                )
            )
        return out


def _config() -> MacroIntelConfig:
    return MacroIntelConfig.model_validate(
        {
            "layers": {
                "regular": [
                    {
                        "query_id": "q1",
                        "topic": "monetary",
                        "layer": "regular",
                        "query": "中国 货币政策",
                        "theme_type": "POLICY_ENVIRONMENT",
                        "language": "zh",
                        "region": "CN",
                        "source_profile": "CN",
                    }
                ],
                "sentinel": [
                    {
                        "query_id": "q2",
                        "topic": "external_shock",
                        "layer": "sentinel",
                        "query": "制裁 油价 汇率",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "zh",
                        "region": "CN",
                        "source_profile": "CN",
                    }
                ],
            },
            "routing": {
                "default_engine": {"zh_cn": "bocha", "en_or_global": "tavily"},
                "dual_search_topics": ["external_shock"],
            },
            "sources": {
                "CN": {"gov.cn": 0.98, "pbc.gov.cn": 0.98, "stcn.com": 0.7},
                "INTL": {"reuters.com": 0.82},
            },
            "engines": {
                "tavily": {"max_results": 5},
                "bocha": {"count": 5},
            },
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
            "upgrade_rules": {
                "keywords": ["制裁", "油价", "汇率"],
                "market_move_keywords": ["oil", "dollar"],
            },
            "dedup": {"title_similarity_threshold": 0.9},
            "cluster": {"time_window_hours": 48, "title_similarity_threshold": 0.86},
        }
    )


def test_router_dual_search_rule() -> None:
    config = _config()
    router = MacroQueryRouter(config.routing)
    specs = config.build_query_specs()
    regular = next(x for x in specs if x.topic == "monetary")
    sentinel = next(x for x in specs if x.topic == "external_shock")

    assert router.resolve_engines(regular) == [SearchEngine.BOCHA]
    assert router.resolve_engines(sentinel) == [SearchEngine.BOCHA, SearchEngine.TAVILY]


def test_pipeline_outputs_events_not_articles() -> None:
    config = _config()
    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1",
            "content": "流动性与汇率稳定",
            "published_at": datetime.now(UTC),
        },
        {
            "title": "地缘冲突升级引发油价上涨",
            "url": "https://www.stcn.com/a2",
            "content": "制裁升级，油价波动，美元走强",
            "published_at": datetime.now(UTC),
        },
    ]
    tavily_rows = [
        {
            "title": "Sanctions escalation drives oil and dollar volatility",
            "url": "https://www.reuters.com/a3",
            "content": "sanctions and oil shock may affect fx and yields",
            "published_at": datetime.now(UTC),
        }
    ]

    pipeline = MacroIntelPipeline(
        config=config,
        clients={
            SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows),
            SearchEngine.TAVILY: FakeClient(SearchEngine.TAVILY, tavily_rows),
        },
    )

    events = pipeline.run(as_of_date=date(2026, 3, 25))

    assert events
    assert all(e.theme_type in {MacroThemeType.POLICY_ENVIRONMENT, MacroThemeType.OVERSEAS_MAPPING} for e in events)
    assert all(e.source_type.value == "NEWS" for e in events)
    # Ensure sentinel topic with dual search can produce one macro candidate event
    assert any("oil" in e.summary.lower() or "油价" in e.summary for e in events)
