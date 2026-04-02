from __future__ import annotations

from datetime import UTC, datetime

from contracts.enums import MacroThemeType
from macro.intel.models import EventCluster, MacroLayer, RawArticle, ScoredEvent, SearchEngine, SearchQuerySpec
from macro.intel.summarizer import _extract_key_numbers, _parse_summary_json, _pick_fact_sentence


def _spec() -> SearchQuerySpec:
    return SearchQuerySpec(
        query_id="q1",
        topic="monetary_policy",
        layer=MacroLayer.REGULAR,
        query="中国人民银行 MLF 利率",
        theme_type=MacroThemeType.POLICY_ENVIRONMENT,
        language="zh",
        region="CN",
        source_profile="CN",
    )


def _article() -> RawArticle:
    return RawArticle.from_web_result(
        engine=SearchEngine.BOCHA,
        spec=_spec(),
        title="中国人民银行维持MLF利率1.5%",
        url="https://example.com/a1",
        content="央行公告显示MLF利率维持1.5%，市场关注后续流动性投放节奏。",
        published_at=datetime(2026, 3, 25, 12, 0, tzinfo=UTC),
        language="zh",
    )


def _scored() -> ScoredEvent:
    article = _article()
    cluster = EventCluster(
        cluster_id="clu:1",
        topic="monetary_policy",
        layer=MacroLayer.REGULAR,
        theme_type=MacroThemeType.POLICY_ENVIRONMENT,
        representative_title=article.title,
        articles=[article],
    )
    return ScoredEvent.model_validate(
        {
            "cluster": cluster.model_dump(),
            "score": 78.5,
            "breakdown": {
                "source_weight": 0.8,
                "event_severity": 0.8,
                "market_impact": 0.7,
                "freshness": 0.8,
                "cross_source_confirm": 0.6,
                "transmission_chain": 0.6,
            },
            "upgraded_to_macro_candidate": True,
            "labels": [],
        }
    )


def test_parse_summary_json_accepts_wrapped_text() -> None:
    text = """
    以下是结果：
    {"summary":"政策操作延续","what_happened":"央行维持MLF利率","why_it_matters":"影响利率预期","market_impact":"利率/汇率","key_numbers":["1.5%"],"policy_signal":"中性维持","confidence":"medium"}
    """
    parsed = _parse_summary_json(text)
    assert parsed is not None
    assert parsed.what_happened == "央行维持MLF利率"
    assert parsed.key_numbers == ["1.5%"]


def test_fallback_extractors_capture_content_signal() -> None:
    scored = _scored()
    sentence = _pick_fact_sentence(scored.cluster.articles)
    numbers = _extract_key_numbers(scored.cluster.articles)

    assert sentence
    assert "1.5%" in sentence or "1.5%" in " ".join(numbers)
    assert numbers
