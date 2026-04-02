from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import MacroThemeType


class MacroLayer(StrEnum):
    REGULAR = "regular"
    SENTINEL = "sentinel"


class SearchEngine(StrEnum):
    TAVILY = "tavily"
    BOCHA = "bocha"


class SearchQuerySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    topic: str
    layer: MacroLayer
    query: str
    theme_type: MacroThemeType
    language: str
    region: str
    source_profile: str
    route: str | None = None
    tavily_profile: str | None = None


class RawArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    engine: SearchEngine
    query_id: str
    topic: str
    layer: MacroLayer
    theme_type: MacroThemeType
    title: str
    url: str
    content: str = ""
    published_at: datetime | None = None
    language: str | None = None
    region: str
    domain: str
    source_name: str | None = None
    raw_score: float | None = None

    @classmethod
    def from_web_result(
        cls,
        *,
        engine: SearchEngine,
        spec: SearchQuerySpec,
        title: str,
        url: str,
        content: str = "",
        published_at: datetime | None = None,
        language: str | None = None,
        source_name: str | None = None,
        raw_score: float | None = None,
    ) -> "RawArticle":
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        article_id = f"{engine.value}:{spec.query_id}:{abs(hash((title, url)))}"
        return cls(
            article_id=article_id,
            engine=engine,
            query_id=spec.query_id,
            topic=spec.topic,
            layer=spec.layer,
            theme_type=spec.theme_type,
            title=title.strip(),
            url=url,
            content=content.strip(),
            published_at=published_at,
            language=language,
            region=spec.region,
            domain=domain,
            source_name=source_name,
            raw_score=raw_score,
        )


class EventCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    topic: str
    layer: MacroLayer
    theme_type: MacroThemeType
    representative_title: str
    articles: list[RawArticle] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def combined_text(self) -> str:
        chunks = [self.representative_title]
        chunks.extend(a.title for a in self.articles)
        chunks.extend(a.content for a in self.articles if a.content)
        return "\n".join(chunks)


class EventScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_weight: float
    event_severity: float
    market_impact: float
    freshness: float
    cross_source_confirm: float
    transmission_chain: float


class ScoredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster: EventCluster
    score: float
    breakdown: EventScoreBreakdown
    upgraded_to_macro_candidate: bool
    labels: list[str] = Field(default_factory=list)


def normalize_title(text: str) -> str:
    return " ".join(text.lower().strip().split())
