from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from typing import Iterable
import uuid

from contracts.confidence import ConfidenceDTO
from contracts.delta import DeltaDTO
from contracts.enums import (
    ConfidenceLevel,
    EntityType,
    MacroBiasTag,
    MacroThemeType,
    SourceType,
)
from contracts.macro_contracts import MacroDeltaDTO, MacroMasterCardDTO, MacroThemeCardSummaryDTO
from contracts.source_refs import SourceRefDTO
from macro.mapper import MacroIndustryMapper
from macro.repository import MacroRepository
from macro.retriever import MacroEvent, MacroRetriever
from macro.triggers import MacroTriggers

_THEME_BIAS_DEFAULT: dict[MacroThemeType, MacroBiasTag] = {
    MacroThemeType.DOMESTIC_AGGREGATE: MacroBiasTag.LIQUIDITY_DOMINANT,
    MacroThemeType.POLICY_ENVIRONMENT: MacroBiasTag.POLICY_EXPECTATION_DOMINANT,
    MacroThemeType.OVERSEAS_MAPPING: MacroBiasTag.EXTERNAL_DISTURBANCE_DOMINANT,
    MacroThemeType.MARKET_STYLE: MacroBiasTag.RISK_APPETITE_RECOVERY,
}

_THEME_SW_DEFAULT: dict[MacroThemeType, dict[str, list[str]]] = {
    MacroThemeType.DOMESTIC_AGGREGATE: {
        "positive": ["801780", "801790", "801050"],
        "negative": ["801120"],
    },
    MacroThemeType.POLICY_ENVIRONMENT: {
        "positive": ["801710", "801740"],
        "negative": ["801020"],
    },
    MacroThemeType.OVERSEAS_MAPPING: {
        "positive": ["801120", "801150"],
        "negative": ["801080", "801140"],
    },
    MacroThemeType.MARKET_STYLE: {
        "positive": ["801750", "801760"],
        "negative": ["801780"],
    },
}


class MacroUpdater:
    def __init__(
        self,
        repository: MacroRepository,
        retriever: MacroRetriever | None = None,
        mapper: MacroIndustryMapper | None = None,
        triggers: MacroTriggers | None = None,
    ):
        self.repository = repository
        self.retriever = retriever or MacroRetriever()
        self.mapper = mapper or MacroIndustryMapper()
        self.triggers = triggers or MacroTriggers()

    def run_daily_incremental_update(
        self,
        as_of_date: date,
        events: list[MacroEvent] | None = None,
    ) -> MacroMasterCardDTO:
        previous = self.repository.get_latest_master(as_of_date=as_of_date)
        daily_events = events if events is not None else self.retriever.fetch_daily_events(as_of_date)

        grouped = self._group_events_by_theme(daily_events)
        changed_theme_cards = self._build_theme_cards(as_of_date=as_of_date, grouped_events=grouped)

        new_biases = self._derive_biases(previous_master=previous, events=daily_events)
        mappings = self.mapper.map_to_sw_l1(biases=new_biases, theme_cards=changed_theme_cards)
        material_change = self.triggers.evaluate_material_change(
            previous_master=previous,
            new_biases=new_biases,
            changed_theme_count=len(changed_theme_cards),
            new_mappings=mappings,
        )

        version = self._next_version(as_of_date=as_of_date, previous_version=previous.version if previous else None)
        key_changes = [e.title for e in daily_events[:5]] or ["无新增高相关宏观事件，维持原判断"]
        risk_opportunity_flags = self._extract_risk_opportunity_flags(daily_events)

        sw_positive = [m.sw_l1_id for m in mappings if m.direction.value == "POSITIVE"]
        sw_negative = [m.sw_l1_id for m in mappings if m.direction.value == "NEGATIVE"]
        sw_neutral = [m.sw_l1_id for m in mappings if m.direction.value == "NEUTRAL"]
        confidence = self._confidence_from_event_count(len(daily_events))

        macro_mainline = self._build_mainline(daily_events=daily_events, previous=previous)
        style_impact = self._build_style_impact(new_biases)
        source_refs = self._build_source_refs(daily_events=daily_events, previous=previous)

        master = MacroMasterCardDTO(
            version=version,
            as_of_date=as_of_date,
            created_at=datetime.now(UTC),
            current_macro_bias=new_biases,
            macro_mainline=macro_mainline,
            key_changes=key_changes,
            risk_opportunity_flags=risk_opportunity_flags,
            a_share_style_impact=style_impact,
            sw_l1_positive=sw_positive,
            sw_l1_negative=sw_negative,
            sw_l1_neutral=sw_neutral,
            reasoning=self._build_reasoning(previous=previous, events=daily_events, biases=new_biases),
            source_refs=source_refs,
            confidence=confidence,
            material_change=material_change,
        )

        self.repository.save_master_snapshot(master)
        for theme in changed_theme_cards:
            self.repository.save_theme_snapshot(theme=theme, version=version)

        for mapping in mappings:
            self.repository.save_industry_mapping(version=version, mapping=mapping, as_of_date=as_of_date)

        delta = self._build_delta(previous=previous, current=master, as_of_date=as_of_date)
        self.repository.save_delta(delta)

        self.repository.save_run_log(
            {
                "run_id": f"macro-run:{as_of_date:%Y%m%d}:{uuid.uuid4().hex[:8]}",
                "as_of_date": as_of_date,
                "event_count": len(daily_events),
                "changed_theme_count": len(changed_theme_cards),
                "material_change": material_change.material_change,
                "status": "SUCCESS",
                "note": f"themes={','.join(t.theme_type.value for t in changed_theme_cards)}",
            }
        )

        return master

    def _group_events_by_theme(self, events: Iterable[MacroEvent]) -> dict[MacroThemeType, list[MacroEvent]]:
        grouped: dict[MacroThemeType, list[MacroEvent]] = defaultdict(list)
        for event in events:
            grouped[event.theme_type].append(event)
        return grouped

    def _build_theme_cards(
        self,
        as_of_date: date,
        grouped_events: dict[MacroThemeType, list[MacroEvent]],
    ) -> list[MacroThemeCardSummaryDTO]:
        cards: list[MacroThemeCardSummaryDTO] = []
        for theme, events in grouped_events.items():
            defaults = _THEME_SW_DEFAULT.get(theme, {"positive": [], "negative": []})
            source_refs = [
                SourceRefDTO(
                    source_type=e.source_type,
                    title=e.title,
                    retrieved_at=datetime.now(UTC),
                    source_id=e.source_id,
                    url=e.url,
                    published_at=e.published_at,
                    provider=e.provider,
                )
                for e in events[:5]
            ]
            risks = [e.title for e in events if any(k in (e.summary + e.title) for k in ["风险", "下行", "扰动", "不确定"])]
            drivers = [e.summary or e.title for e in events[:4]]

            cards.append(
                MacroThemeCardSummaryDTO(
                    theme_type=theme,
                    as_of_date=as_of_date,
                    current_view=f"{theme.value}：{'；'.join(e.title for e in events[:2])}",
                    latest_changes=[e.title for e in events[:5]],
                    drivers=drivers,
                    risks=risks[:4],
                    a_share_style_impact=self._theme_style_impact(theme),
                    sw_l1_positive=defaults["positive"],
                    sw_l1_negative=defaults["negative"],
                    sw_l1_neutral=[],
                    reasoning=f"基于{len(events)}条事件进行{theme.value}增量更新。",
                    source_refs=source_refs,
                    confidence=self._confidence_from_event_count(len(events)),
                )
            )
        return cards

    def _derive_biases(
        self,
        previous_master: MacroMasterCardDTO | None,
        events: list[MacroEvent],
    ) -> list[MacroBiasTag]:
        if not events:
            if previous_master:
                return previous_master.current_macro_bias
            return [MacroBiasTag.POLICY_EXPECTATION_DOMINANT]

        counter: Counter[MacroBiasTag] = Counter()
        for event in events:
            if event.bias_hint:
                counter[event.bias_hint] += 2
            counter[_THEME_BIAS_DEFAULT[event.theme_type]] += 1

        if previous_master:
            for bias in previous_master.current_macro_bias:
                counter[bias] += 1

        ordered = [bias for bias, _ in counter.most_common(3)]
        return ordered or [MacroBiasTag.POLICY_EXPECTATION_DOMINANT]

    def _build_mainline(self, daily_events: list[MacroEvent], previous: MacroMasterCardDTO | None) -> str:
        if daily_events:
            return "；".join(event.title for event in daily_events[:2])
        if previous:
            return previous.macro_mainline
        return "暂无新增宏观主线，等待高相关事件触发更新。"

    def _build_style_impact(self, biases: list[MacroBiasTag]) -> str:
        if MacroBiasTag.DEFENSIVE_PREFERENCE_RISING in biases:
            return "防御风格相对占优，成长风格弹性受约束。"
        if MacroBiasTag.RISK_APPETITE_RECOVERY in biases or MacroBiasTag.THEMATIC_RISK_APPETITE_DOMINANT in biases:
            return "风险偏好边际修复，成长和主题风格更活跃。"
        if MacroBiasTag.PRO_CYCLICAL_TRADING_WARMING in biases:
            return "顺周期风格活跃度提升，价值与周期板块相对占优。"
        return "风格分化延续，建议保持均衡配置并跟踪增量信号。"

    def _build_reasoning(
        self,
        previous: MacroMasterCardDTO | None,
        events: list[MacroEvent],
        biases: list[MacroBiasTag],
    ) -> str:
        if not previous:
            return f"首次建立宏观基线，基于{len(events)}条事件归纳当前bias。"
        return f"本次新增{len(events)}条事件，bias更新为{','.join(b.value for b in biases)}。"

    def _build_source_refs(
        self,
        daily_events: list[MacroEvent],
        previous: MacroMasterCardDTO | None,
    ) -> list[SourceRefDTO]:
        if daily_events:
            refs: list[SourceRefDTO] = []
            for event in daily_events[:8]:
                refs.append(
                    SourceRefDTO(
                        source_type=event.source_type,
                        title=event.title,
                        retrieved_at=datetime.now(UTC),
                        source_id=event.source_id,
                        url=event.url,
                        published_at=event.published_at,
                        provider=event.provider,
                    )
                )
            return refs
        if previous:
            return previous.source_refs
        return [
            SourceRefDTO(
                source_type=SourceType.INTERNAL_SUMMARY,
                title="macro-initial-placeholder",
                retrieved_at=datetime.now(UTC),
                note="No external event provided",
            )
        ]

    def _build_delta(
        self,
        previous: MacroMasterCardDTO | None,
        current: MacroMasterCardDTO,
        as_of_date: date,
    ) -> MacroDeltaDTO:
        if previous is None:
            changed_fields = [
                "current_macro_bias",
                "macro_mainline",
                "key_changes",
                "risk_opportunity_flags",
                "a_share_style_impact",
                "sw_l1_positive",
                "sw_l1_negative",
                "sw_l1_neutral",
                "material_change",
            ]
            summary = "Initial macro baseline created."
        else:
            changed_fields = []
            tracked_fields = [
                "current_macro_bias",
                "macro_mainline",
                "key_changes",
                "risk_opportunity_flags",
                "a_share_style_impact",
                "sw_l1_positive",
                "sw_l1_negative",
                "sw_l1_neutral",
            ]
            previous_payload = previous.model_dump(mode="json")
            current_payload = current.model_dump(mode="json")
            for field in tracked_fields:
                if previous_payload[field] != current_payload[field]:
                    changed_fields.append(field)
            if previous.material_change != current.material_change:
                changed_fields.append("material_change")
            summary = (
                "No significant top-level field changes."
                if not changed_fields
                else f"Changed fields: {', '.join(changed_fields)}"
            )

        base_delta = DeltaDTO(
            delta_id=f"macro-delta:{as_of_date:%Y%m%d}:{uuid.uuid4().hex[:8]}",
            entity_type=EntityType.MACRO_MASTER,
            entity_id="macro_master",
            from_version=previous.version if previous else "NONE",
            to_version=current.version,
            as_of_date=as_of_date,
            changed_fields=changed_fields,
            summary=summary,
            reasons=current.material_change.reasons,
            impact_scope=["macro_master", "industry_constraints"],
            material_change=current.material_change,
            source_refs=current.source_refs[:5],
            created_at=datetime.now(UTC),
        )
        return MacroDeltaDTO.model_validate(base_delta.model_dump(mode="json"))

    def _extract_risk_opportunity_flags(self, events: list[MacroEvent]) -> list[str]:
        flags: list[str] = []
        for event in events:
            text = f"{event.title}{event.summary}"
            if any(keyword in text for keyword in ["风险", "下行", "扰动", "不确定"]):
                flags.append(f"风险:{event.title}")
            if any(keyword in text for keyword in ["改善", "回升", "修复", "利好"]):
                flags.append(f"机会:{event.title}")
        return flags[:8] or ["中性:暂无新增显著风险/机会信号"]

    def _theme_style_impact(self, theme: MacroThemeType) -> str:
        mapping = {
            MacroThemeType.DOMESTIC_AGGREGATE: "总量信号变化对大盘价值风格更敏感。",
            MacroThemeType.POLICY_ENVIRONMENT: "政策预期对主题与顺周期风格有边际影响。",
            MacroThemeType.OVERSEAS_MAPPING: "海外扰动影响外需链与高弹性科技板块。",
            MacroThemeType.MARKET_STYLE: "市场风格信号直接影响成长/价值切换节奏。",
        }
        return mapping[theme]

    def _confidence_from_event_count(self, event_count: int) -> ConfidenceDTO:
        if event_count >= 4:
            return ConfidenceDTO(score=0.82, level=ConfidenceLevel.HIGH, note="Multiple high-relevance events")
        if event_count >= 2:
            return ConfidenceDTO(score=0.68, level=ConfidenceLevel.MEDIUM, note="Limited but meaningful events")
        return ConfidenceDTO(score=0.55, level=ConfidenceLevel.MEDIUM, note="Sparse event coverage")

    def _next_version(self, as_of_date: date, previous_version: str | None) -> str:
        prefix = f"macro-master:{as_of_date:%Y%m%d}:"
        if not previous_version or not previous_version.startswith(prefix):
            return f"{prefix}01"
        try:
            seq = int(previous_version.split(":")[-1]) + 1
        except ValueError:
            seq = 1
        return f"{prefix}{seq:02d}"
