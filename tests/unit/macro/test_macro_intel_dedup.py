from __future__ import annotations

from datetime import UTC, datetime

from contracts.enums import MacroThemeType
from macro.intel.dedup import DocumentDeduplicator
from macro.intel.models import MacroLayer, RawArticle, SearchEngine, SearchQuerySpec


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


def _row(*, title: str, url: str, content: str, published_at: datetime) -> RawArticle:
    return RawArticle.from_web_result(
        engine=SearchEngine.BOCHA,
        spec=_spec(),
        title=title,
        url=url,
        content=content,
        published_at=published_at,
        language="zh",
    )


def test_dedup_with_structured_keys_removes_same_event() -> None:
    now = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    rows = [
        _row(
            title="央行开展MLF操作 1.5% 利率维持不变",
            url="https://a.example.com/1",
            content="中国人民银行维持1.5%利率，强调流动性合理充裕。",
            published_at=now,
        ),
        _row(
            title="PBOC keeps MLF rate steady at 1.5 percent",
            url="https://b.example.com/2",
            content="PBC said liquidity conditions remain stable at 1.5%.",
            published_at=now,
        ),
    ]

    dedup = DocumentDeduplicator(
        title_similarity_threshold=0.98,
        by=["institution", "event_type", "time_window", "key_figures"],
        time_window_hours=72,
    )
    kept = dedup.dedup(rows)

    assert len(kept) == 1


def test_dedup_respects_time_window_for_structured_match() -> None:
    t1 = datetime(2026, 3, 25, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 29, 12, 0, tzinfo=UTC)  # 96h later
    rows = [
        _row(
            title="央行开展MLF操作 1.5% 利率维持不变",
            url="https://a.example.com/1",
            content="中国人民银行维持1.5%利率，强调流动性合理充裕。",
            published_at=t1,
        ),
        _row(
            title="PBOC keeps MLF rate steady at 1.5 percent",
            url="https://b.example.com/2",
            content="PBC said liquidity conditions remain stable at 1.5%.",
            published_at=t2,
        ),
    ]

    dedup = DocumentDeduplicator(
        title_similarity_threshold=0.98,
        by=["institution", "event_type", "time_window", "key_figures"],
        time_window_hours=72,
    )
    kept = dedup.dedup(rows)

    assert len(kept) == 2
