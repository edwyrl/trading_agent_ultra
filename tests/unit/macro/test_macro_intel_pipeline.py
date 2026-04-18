from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta

from contracts.enums import MacroThemeType
from macro.intel.config import MacroIntelConfig
from macro.intel.models import RawArticle, SearchEngine, SearchQuerySpec
from macro.intel.pipeline import MacroIntelPipeline
from macro.intel.router import MacroQueryRouter
from macro.intel.summarizer import MacroSummaryResult


class FakeClient:
    def __init__(self, engine: SearchEngine, rows: list[dict]):
        self.engine = engine
        self.rows = rows

    def search(
        self,
        spec: SearchQuerySpec,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawArticle]:
        _ = (include_domains, exclude_domains)
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


class StubEditor:
    def __init__(self, text: str):
        self.text = text

    def generate(self, *, scored, region: str, category: str) -> str:  # noqa: ANN001
        _ = (scored, region, category)
        return self.text


class StubSummarizer:
    def __init__(self, summary: str):
        self.summary = summary

    def summarize(self, *, scored, region: str, category: str) -> MacroSummaryResult:  # noqa: ANN001
        _ = (scored, region, category)
        return MacroSummaryResult(
            summary=self.summary,
            what_happened="事件已发生",
            why_it_matters="将影响政策预期与利率定价。",
            market_impact="利率/汇率",
            key_numbers=["1.5%"],
            policy_signal="中性维持",
            confidence="medium",
        )


class SpecAwareClient:
    def __init__(self, engine: SearchEngine):
        self.engine = engine

    def search(
        self,
        spec: SearchQuerySpec,
        *,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> list[RawArticle]:
        _ = (include_domains, exclude_domains)
        order_map = {
            "q_cn_1": 1,
            "q_cn_2": 2,
            "q_us_1": 3,
            "q_us_2": 4,
            "q_cross_fx_1": 5,
            "q_cross_fx_2": 6,
            "q_cross_com": 7,
        }
        order = order_map.get(spec.query_id, 99)
        ts = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
        published = ts.replace(minute=max(0, 60 - order))
        return [
            RawArticle.from_web_result(
                engine=self.engine,
                spec=spec,
                title=f"{spec.region}-{spec.topic}-{spec.query_id} signal",
                url=f"https://example.com/{spec.query_id}",
                content=f"{spec.topic} signal transmission to liquidity and fx",
                published_at=published,
                language=spec.language,
            )
        ]


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


def _config_with_quotas() -> MacroIntelConfig:
    return MacroIntelConfig.model_validate(
        {
            "layers": {
                "regular": [
                    {
                        "query_id": "q_cn_1",
                        "topic": "monetary",
                        "layer": "regular",
                        "query": "cn1",
                        "theme_type": "POLICY_ENVIRONMENT",
                        "language": "zh",
                        "region": "CN",
                        "source_profile": "CN",
                    },
                    {
                        "query_id": "q_cn_2",
                        "topic": "growth",
                        "layer": "regular",
                        "query": "cn2",
                        "theme_type": "DOMESTIC_AGGREGATE",
                        "language": "zh",
                        "region": "CN",
                        "source_profile": "CN",
                    },
                    {
                        "query_id": "q_us_1",
                        "topic": "inflation",
                        "layer": "regular",
                        "query": "us1",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "en",
                        "region": "US",
                        "source_profile": "INTL",
                    },
                    {
                        "query_id": "q_us_2",
                        "topic": "labor",
                        "layer": "regular",
                        "query": "us2",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "en",
                        "region": "US",
                        "source_profile": "INTL",
                    },
                    {
                        "query_id": "q_cross_fx_1",
                        "topic": "fx",
                        "layer": "regular",
                        "query": "cross_fx_1",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "en",
                        "region": "Cross",
                        "source_profile": "INTL",
                    },
                    {
                        "query_id": "q_cross_fx_2",
                        "topic": "fx",
                        "layer": "regular",
                        "query": "cross_fx_2",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "en",
                        "region": "Cross",
                        "source_profile": "INTL",
                    },
                    {
                        "query_id": "q_cross_com",
                        "topic": "commodities",
                        "layer": "regular",
                        "query": "cross_com",
                        "theme_type": "OVERSEAS_MAPPING",
                        "language": "en",
                        "region": "Cross",
                        "source_profile": "INTL",
                    },
                ],
                "sentinel": [],
            },
            "routing": {
                "default_engine": {"zh_cn": "bocha", "en_or_global": "bocha"},
                "dual_search_topics": [],
            },
            "sources": {
                "CN": {"gov.cn": 0.98},
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
                "keywords": ["signal"],
                "market_move_keywords": [],
            },
            "dedup": {"title_similarity_threshold": 0.9},
            "cluster": {"time_window_hours": 48, "title_similarity_threshold": 0.86},
            "quotas": {
                "cn_top": 1,
                "us_top": 1,
                "cross_market_top": 2,
                "max_same_topic_items": 1,
            },
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


def test_router_respects_explicit_query_route() -> None:
    config = _config()
    router = MacroQueryRouter(config.routing)
    specs = config.build_query_specs()
    regular = next(x for x in specs if x.topic == "monetary")

    forced_tavily = regular.model_copy(update={"route": "tavily"})
    forced_dual = regular.model_copy(update={"route": "dual"})
    forced_bocha = regular.model_copy(update={"route": "bocha"})

    assert router.resolve_engines(forced_tavily) == [SearchEngine.TAVILY]
    assert router.resolve_engines(forced_dual) == [SearchEngine.BOCHA, SearchEngine.TAVILY]
    assert router.resolve_engines(forced_bocha) == [SearchEngine.BOCHA]


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


def test_pipeline_uses_structured_summarizer_for_event_summary() -> None:
    config = _config()
    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1",
            "content": "流动性与汇率稳定",
            "published_at": datetime.now(UTC),
        }
    ]
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
        summarizer=StubSummarizer("结构化摘要：政策操作延续，流动性保持平稳。"),
    )

    events = pipeline.run(as_of_date=date(2026, 3, 25))

    assert events
    assert events[0].summary == "结构化摘要：政策操作延续，流动性保持平稳。"


def test_pipeline_writes_overwrite_log_with_required_fields(tmp_path) -> None:
    config = _config()
    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1",
            "content": "流动性与汇率稳定",
            "published_at": datetime.now(UTC),
        }
    ]
    log_path = tmp_path / "macro_intel_latest.json"

    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
        event_log_path=str(log_path),
        editor=StubEditor("该事件可能影响政策预期与利率定价。"),
    )

    _ = pipeline.run(as_of_date=date(2026, 3, 25))
    first = json.loads(log_path.read_text(encoding="utf-8"))
    assert first["event_count"] >= 1
    assert first["search_usage"]["call_count"]["bocha"] == 2
    assert first["search_usage"]["call_count"]["tavily"] == 0
    assert first["search_usage"]["api_attempts"]["bocha"] == 2
    entry = first["events"][0]
    assert {"region", "category", "why_it_matters", "score"} <= set(entry.keys())
    assert {"summary", "key_numbers", "policy_signal", "confidence"} <= set(entry.keys())
    assert entry["why_it_matters"] == "该事件可能影响政策预期与利率定价。"

    pipeline_empty = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, [])},
        event_log_path=str(log_path),
    )
    _ = pipeline_empty.run(as_of_date=date(2026, 3, 26))
    second = json.loads(log_path.read_text(encoding="utf-8"))
    assert second["as_of_date"] == "2026-03-26"
    assert second["event_count"] == 0
    assert second["search_usage"]["call_count"]["bocha"] == 2
    assert second["events"] == []


def test_pipeline_warns_when_search_usage_exceeds_threshold(caplog) -> None:
    config_payload = _config().model_dump()
    config_payload["usage_alert"] = {
        "bocha_call_warn": 0,
        "tavily_call_warn": 0,
        "bocha_attempt_warn": 0,
        "tavily_attempt_warn": 0,
    }
    config = MacroIntelConfig.model_validate(config_payload)
    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1",
            "content": "流动性与汇率稳定",
            "published_at": datetime.now(UTC),
        }
    ]

    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
    )

    with caplog.at_level(logging.WARNING):
        _ = pipeline.run(as_of_date=date(2026, 3, 25))

    assert any("macro_intel_search_usage_alert" in rec.message and "engine=bocha" in rec.message for rec in caplog.records)


def test_pipeline_applies_region_and_topic_quotas() -> None:
    config = _config_with_quotas()
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: SpecAwareClient(SearchEngine.BOCHA)},
    )

    events = pipeline.run(as_of_date=date(2026, 3, 25))
    titles = [e.title for e in events]

    assert len(events) == 4
    assert sum(t.startswith("CN-") for t in titles) == 1
    assert sum(t.startswith("US-") for t in titles) == 1
    assert sum(t.startswith("Cross-") for t in titles) == 2
    assert sum("-fx-" in t for t in titles) == 1


def test_pipeline_event_id_is_stable_across_dates() -> None:
    config_payload = _config().model_dump()
    config_payload["layers"]["sentinel"] = []
    config = MacroIntelConfig.model_validate(config_payload)

    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1?tracking=abc",
            "content": "流动性与汇率稳定",
            "published_at": datetime(2026, 3, 25, 10, 0, tzinfo=UTC),
        }
    ]
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
    )

    first = pipeline.run(as_of_date=date(2026, 3, 25))
    second = pipeline.run(as_of_date=date(2026, 3, 26))

    assert first and second
    assert [e.event_id for e in first] == [e.event_id for e in second]
    assert [e.source_id for e in first] == [e.source_id for e in second]
    assert all("20260325" not in e.event_id and "20260326" not in e.event_id for e in first + second)


def test_pipeline_blacklist_domains_are_hard_dropped() -> None:
    config_payload = _config().model_dump()
    config_payload["source_policy"] = {
        "deny_domains": ["blocked.example.com"],
    }
    config_payload["scoring"]["thresholds"]["medium"] = 0
    config_payload["scoring"]["thresholds"]["high"] = 100
    config = MacroIntelConfig.model_validate(config_payload)

    bocha_rows = [
        {
            "title": "央行流动性操作",
            "url": "https://blocked.example.com/a1",
            "content": "政策动态",
            "published_at": datetime.now(UTC),
        },
        {
            "title": "央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a2",
            "content": "政策动态",
            "published_at": datetime.now(UTC),
        },
    ]
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
    )

    events = pipeline.run(as_of_date=date(2026, 3, 25))

    assert events
    assert all("blocked.example.com" not in (e.url or "") for e in events)


def test_pipeline_enforces_required_fields_and_editor_policy(tmp_path) -> None:
    config_payload = _config().model_dump()
    config_payload["output"] = {
        "format": "json",
        "required_fields": [
            "title",
            "region",
            "category",
            "what_happened",
            "why_it_matters",
            "market_impact",
            "score",
            "sources",
            "published_at",
        ],
    }
    config_payload["llm_editor_policy"] = {
        "rules": [
            "只保留过去72小时内最重要的事件",
            "忽略纯评论、传闻、无新增事实文章",
        ]
    }
    config = MacroIntelConfig.model_validate(config_payload)

    now = datetime.now(UTC)
    old = now - timedelta(hours=100)
    bocha_rows = [
        {
            "title": "中国央行公开市场操作维持流动性",
            "url": "https://www.pbc.gov.cn/a1",
            "content": "流动性与汇率稳定，油价波动关注",
            "published_at": now,
        },
        {
            "title": "市场传闻：油价评论文章",
            "url": "https://www.stcn.com/a2",
            "content": "rumor opinion without facts but oil mention",
            "published_at": old,
        },
    ]
    log_path = tmp_path / "macro_intel_latest.json"
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
        event_log_path=str(log_path),
        editor=StubEditor("该事件对利率与风险偏好有边际影响。"),
    )

    _ = pipeline.run(as_of_date=date(2026, 3, 25))
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    entry = payload["events"][0]
    for key in config.output.required_fields:
        assert key in entry


def test_pipeline_writes_eval_pack_with_reject_reasons(tmp_path) -> None:
    config = _config_with_quotas()
    eval_pack_path = tmp_path / "macro_eval_pack_latest.json"
    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: SpecAwareClient(SearchEngine.BOCHA)},
        eval_pack_path=str(eval_pack_path),
    )

    _ = pipeline.run(as_of_date=date(2026, 3, 25))
    payload = json.loads(eval_pack_path.read_text(encoding="utf-8"))

    assert payload["as_of_date"] == "2026-03-25"
    assert payload["targets"]["selected"] == 6
    assert payload["targets"]["non_selected"] == 6
    assert isinstance(payload["samples"], list)
    assert payload["selected_count"] <= 6
    assert payload["non_selected_count"] <= 6

    non_selected = payload["non_selected_samples"]
    assert non_selected
    reasons = {row.get("reject_reason") for row in non_selected}
    assert any(reason in {"quota_cn", "quota_us", "quota_cross", "quota_topic"} for reason in reasons)
    required = {"sample_id", "event_id", "topic", "title", "url", "score", "source_domain", "selected"}
    assert required <= set(non_selected[0].keys())


def test_pipeline_eval_pack_fills_from_cluster_when_non_selected_pool_is_small(tmp_path) -> None:
    config_payload = _config().model_dump()
    config_payload["scoring"]["thresholds"]["medium"] = 95
    config_payload["scoring"]["thresholds"]["high"] = 99
    config_payload["upgrade_rules"] = {"keywords": [], "market_move_keywords": []}
    config_payload["dedup"] = {
        "title_similarity_threshold": 0.9,
        "by": ["institution", "event_type", "key_figures", "time_window"],
        "time_window_hours": 12,
    }
    config_payload["layers"] = {
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
        "sentinel": [],
    }
    config = MacroIntelConfig.model_validate(config_payload)
    eval_pack_path = tmp_path / "macro_eval_pack_latest.json"
    now = datetime.now(UTC)
    bocha_rows = [
        {
            "title": "政策信号观察",
            "url": f"https://unknown-source.example.com/a{i}",
            "content": "普通新闻，无升级关键词",
            "published_at": now - timedelta(minutes=i),
        }
        for i in range(8)
    ]

    pipeline = MacroIntelPipeline(
        config=config,
        clients={SearchEngine.BOCHA: FakeClient(SearchEngine.BOCHA, bocha_rows)},
        eval_pack_path=str(eval_pack_path),
    )
    _ = pipeline.run(as_of_date=date(2026, 3, 25))

    payload = json.loads(eval_pack_path.read_text(encoding="utf-8"))
    non_selected = payload["non_selected_samples"]
    assert len(non_selected) == 6
    assert any(row.get("low_pool_fill") is True for row in non_selected)
    assert any(row.get("reject_reason") == "dedup_or_clustered" for row in non_selected)
