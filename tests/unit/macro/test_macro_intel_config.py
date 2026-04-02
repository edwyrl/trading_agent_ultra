from __future__ import annotations

from pathlib import Path

from macro.intel.config import load_macro_intel_config


def test_load_legacy_macro_intel_config_still_works() -> None:
    config = load_macro_intel_config(Path("macro/config/macro_intel.yaml"))
    specs = config.build_query_specs()

    assert len(specs) == 5
    assert config.routing.default_engine["zh_cn"] == "bocha"
    assert config.routing.default_engine["en_or_global"] == "tavily"
    assert config.scoring.thresholds.high == 75.0
    assert config.scoring.thresholds.medium == 55.0


def test_load_v1_1_macro_intel_config_is_mapped_to_runtime_schema() -> None:
    config = load_macro_intel_config(Path("macro/config/macro_intel_v1_1.yaml"))
    specs = config.build_query_specs()

    assert specs
    assert any(spec.layer.value == "regular" for spec in specs)
    assert any(spec.layer.value == "sentinel" for spec in specs)
    assert any(spec.topic == "geopolitics" for spec in specs)
    assert any(spec.topic == "financial_stability" for spec in specs)

    assert "geopolitics" in config.routing.dual_search_topics
    assert "financial_stability" in config.routing.dual_search_topics
    assert "fx" in config.routing.dual_search_topics

    assert config.scoring.thresholds.high == 75.0
    assert config.scoring.thresholds.medium == 60.0
    assert config.cluster.time_window_hours == 72
    assert config.quotas.cn_top == 3
    assert config.quotas.us_top == 3
    assert config.quotas.cross_market_top == 2
    assert config.quotas.max_same_topic_items == 2
    assert "institution" in config.dedup.by
    assert "event_type" in config.dedup.by
    assert "time_window" in config.dedup.by
    assert config.dedup.time_window_hours == 72
    assert "why_it_matters" in config.output.required_fields
    assert "score" in config.output.required_fields
    assert config.llm_editor_policy.rules

    assert config.sources["CN"]["pbc.gov.cn"] > config.sources["CN"]["caixin.com"]
    assert config.sources["INTL"]["federalreserve.gov"] > config.sources["INTL"]["reuters.com"]

    assert "制裁" in config.upgrade_rules.keywords
    assert "oil" in config.upgrade_rules.market_move_keywords

    us_treasury = next(spec for spec in specs if spec.query_id.startswith("regular_us_treasury_en_"))
    assert us_treasury.route == "tavily"
    assert us_treasury.tavily_profile == "finance"
