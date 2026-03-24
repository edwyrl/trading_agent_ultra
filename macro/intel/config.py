from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import MacroThemeType
from macro.intel.models import MacroLayer, SearchQuerySpec


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_engine: dict[str, str]
    dual_search_topics: list[str] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_weight: float
    event_severity: float
    market_impact: float
    freshness: float
    cross_source_confirm: float
    transmission_chain: float


class ScoringThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high: float = 75.0
    medium: float = 55.0


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: ScoringWeights
    thresholds: ScoringThresholds


class UpgradeRulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[str] = Field(default_factory=list)
    market_move_keywords: list[str] = Field(default_factory=list)


class DedupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_similarity_threshold: float = 0.9


class ClusterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_window_hours: int = 48
    title_similarity_threshold: float = 0.86


class MacroIntelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layers: dict[str, list[dict]]
    routing: RoutingConfig
    sources: dict[str, dict[str, float]]
    engines: dict[str, dict]
    scoring: ScoringConfig
    upgrade_rules: UpgradeRulesConfig
    dedup: DedupConfig
    cluster: ClusterConfig

    def build_query_specs(self) -> list[SearchQuerySpec]:
        specs: list[SearchQuerySpec] = []
        for layer_name, rows in self.layers.items():
            layer = MacroLayer(layer_name)
            for row in rows:
                specs.append(
                    SearchQuerySpec(
                        query_id=row["query_id"],
                        topic=row["topic"],
                        layer=layer,
                        query=row["query"],
                        theme_type=MacroThemeType(row["theme_type"]),
                        language=row.get("language", "zh"),
                        region=row.get("region", "CN"),
                        source_profile=row.get("source_profile", "CN"),
                    )
                )
        return specs


def load_macro_intel_config(path: str | Path) -> MacroIntelConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return MacroIntelConfig.model_validate(raw)
