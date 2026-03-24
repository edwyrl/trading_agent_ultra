from __future__ import annotations

from macro.intel.config import RoutingConfig
from macro.intel.models import SearchEngine, SearchQuerySpec


class MacroQueryRouter:
    def __init__(self, config: RoutingConfig):
        self.config = config

    def resolve_engines(self, spec: SearchQuerySpec) -> list[SearchEngine]:
        dual_topics = {t.lower() for t in self.config.dual_search_topics}
        if spec.topic.lower() in dual_topics:
            return [SearchEngine.BOCHA, SearchEngine.TAVILY]

        lang = spec.language.lower()
        region = spec.region.upper()
        if lang.startswith("zh") and region == "CN":
            default = self.config.default_engine.get("zh_cn", "bocha")
        else:
            default = self.config.default_engine.get("en_or_global", "tavily")
        return [SearchEngine(default)]

    def is_dual_search(self, spec: SearchQuerySpec) -> bool:
        engines = self.resolve_engines(spec)
        return len(engines) > 1
