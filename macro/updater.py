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
    MacroEventStatus,
    MacroEventViewType,
    MacroThemeType,
    MappingDirection,
    SourceType,
)
from contracts.macro_contracts import (
    MacroDeltaDTO,
    MacroEventHistoryDTO,
    MacroEventViewDTO,
    MacroMasterCardDTO,
    MacroThemeCardSummaryDTO,
)
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

_NEGATIVE_THEME_BIAS: dict[MacroThemeType, MacroBiasTag] = {
    MacroThemeType.DOMESTIC_AGGREGATE: MacroBiasTag.DEFENSIVE_PREFERENCE_RISING,
    MacroThemeType.POLICY_ENVIRONMENT: MacroBiasTag.DEFENSIVE_PREFERENCE_RISING,
    MacroThemeType.OVERSEAS_MAPPING: MacroBiasTag.EXTERNAL_DISTURBANCE_DOMINANT,
    MacroThemeType.MARKET_STYLE: MacroBiasTag.DEFENSIVE_PREFERENCE_RISING,
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
        incoming_events = events if events is not None else self.retriever.fetch_daily_events(as_of_date)
        ingested = self._persist_event_history_and_views(as_of_date=as_of_date, events=incoming_events)
        self._flush_repository_writes()

        active_histories = self.repository.list_latest_event_history(as_of_date=as_of_date)
        active_events = self._events_from_histories(active_histories)
        history_ids = [h.history_id for h in active_histories]
        active_views = self.repository.list_event_views(history_ids=history_ids, as_of_date=as_of_date)
        view_scores = self._build_event_view_scores(active_views)

        today_histories = [h for h in active_histories if h.as_of_date == as_of_date]
        today_events = self._events_from_histories(today_histories)
        grouped = self._group_events_by_theme(today_events)
        changed_theme_cards = self._build_theme_cards(
            as_of_date=as_of_date,
            grouped_events=grouped,
            view_scores=view_scores,
            views=active_views,
        )

        new_biases = self._derive_biases(previous_master=previous, events=active_events, view_scores=view_scores)
        mappings = self.mapper.map_to_sw_l1(biases=new_biases, theme_cards=changed_theme_cards)
        material_change = self.triggers.evaluate_material_change(
            previous_master=previous,
            new_biases=new_biases,
            changed_theme_count=len(changed_theme_cards),
            new_mappings=mappings,
        )

        version = self._next_version(as_of_date=as_of_date, previous_version=previous.version if previous else None)
        key_changes = [e.title for e in today_events[:5]] or ["无新增高相关宏观事件，维持原判断"]
        risk_opportunity_flags = self._extract_risk_opportunity_flags(today_events)

        sw_positive = [m.sw_l1_id for m in mappings if m.direction.value == "POSITIVE"]
        sw_negative = [m.sw_l1_id for m in mappings if m.direction.value == "NEGATIVE"]
        sw_neutral = [m.sw_l1_id for m in mappings if m.direction.value == "NEUTRAL"]
        confidence = self._confidence_from_event_count(len(today_events))

        macro_mainline = self._build_mainline(daily_events=today_events, previous=previous)
        style_impact = self._build_style_impact(new_biases)
        source_refs = self._build_source_refs(today_histories=today_histories, previous=previous)
        evidence_event_ids = [h.event_id for h in active_histories[:50]]
        evidence_view_ids = [v.view_id for v in active_views[:100]]

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
            reasoning=self._build_reasoning(previous=previous, events=today_events, biases=new_biases),
            source_refs=source_refs,
            confidence=confidence,
            material_change=material_change,
            evidence_event_ids=evidence_event_ids,
            evidence_view_ids=evidence_view_ids,
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
                "event_count": len(today_events),
                "changed_theme_count": len(changed_theme_cards),
                "material_change": material_change.material_change,
                "status": "SUCCESS",
                "note": (
                    f"themes={','.join(t.theme_type.value for t in changed_theme_cards)};"
                    f"ingested_histories={ingested['history_count']};ingested_views={ingested['view_count']}"
                ),
            }
        )

        return master

    def _flush_repository_writes(self) -> None:
        session = getattr(self.repository, "session", None)
        if session is None:
            return
        flush = getattr(session, "flush", None)
        if callable(flush):
            flush()

    def _group_events_by_theme(self, events: Iterable[MacroEvent]) -> dict[MacroThemeType, list[MacroEvent]]:
        grouped: dict[MacroThemeType, list[MacroEvent]] = defaultdict(list)
        for event in events:
            grouped[event.theme_type].append(event)
        return grouped

    def _build_theme_cards(
        self,
        as_of_date: date,
        grouped_events: dict[MacroThemeType, list[MacroEvent]],
        view_scores: dict[str, dict[str, float]],
        views: list[MacroEventViewDTO],
    ) -> list[MacroThemeCardSummaryDTO]:
        cards: list[MacroThemeCardSummaryDTO] = []
        view_ids_by_event: dict[str, list[str]] = defaultdict(list)
        for view in views:
            view_ids_by_event[view.event_id].append(view.view_id)
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
            evidence_event_ids = [e.event_id for e in events]
            evidence_view_ids: list[str] = []
            for event in events:
                evidence_view_ids.extend(view_ids_by_event.get(event.event_id, []))
            avg_view_score = self._average_theme_view_score(events=events, view_scores=view_scores)

            cards.append(
                MacroThemeCardSummaryDTO(
                    theme_type=theme,
                    as_of_date=as_of_date,
                    current_view=f"{theme.value}：{'；'.join(e.title for e in events[:2])}（观点强度{avg_view_score:.2f}）",
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
                    evidence_event_ids=evidence_event_ids,
                    evidence_view_ids=evidence_view_ids[:50],
                )
            )
        return cards

    def _derive_biases(
        self,
        previous_master: MacroMasterCardDTO | None,
        events: list[MacroEvent],
        view_scores: dict[str, dict[str, float]] | None = None,
    ) -> list[MacroBiasTag]:
        if not events:
            if previous_master:
                return previous_master.current_macro_bias
            return [MacroBiasTag.POLICY_EXPECTATION_DOMINANT]

        score_map = view_scores or {}
        counter: Counter[MacroBiasTag] = Counter()
        for event in events:
            if event.bias_hint:
                counter[event.bias_hint] += 2
            base_bias = _THEME_BIAS_DEFAULT[event.theme_type]
            counter[base_bias] += 1
            view = score_map.get(event.event_id)
            if view:
                net = view["net"]
                strength = max(0.5, min(view["strength"], 2.0))
                if net >= 0.2:
                    counter[base_bias] += strength
                elif net <= -0.2:
                    counter[_NEGATIVE_THEME_BIAS[event.theme_type]] += strength

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
        today_histories: list[MacroEventHistoryDTO],
        previous: MacroMasterCardDTO | None,
    ) -> list[SourceRefDTO]:
        if today_histories:
            refs: list[SourceRefDTO] = []
            for history in today_histories[:8]:
                if history.source_refs:
                    refs.extend(history.source_refs[:2])
                else:
                    refs.append(
                        SourceRefDTO(
                            source_type=SourceType.INTERNAL_SUMMARY,
                            title=history.title,
                            retrieved_at=datetime.now(UTC),
                            note="No source refs in event history",
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

    def _events_from_histories(self, histories: list[MacroEventHistoryDTO]) -> list[MacroEvent]:
        events: list[MacroEvent] = []
        for history in histories:
            first_ref = history.source_refs[0] if history.source_refs else None
            events.append(
                MacroEvent(
                    event_id=history.event_id,
                    title=history.title,
                    summary=history.fact_summary,
                    theme_type=history.theme_type,
                    source_type=first_ref.source_type if first_ref else SourceType.INTERNAL_SUMMARY,
                    published_at=first_ref.published_at if first_ref else None,
                    url=first_ref.url if first_ref else None,
                    source_id=first_ref.source_id if first_ref else history.history_id,
                    provider=first_ref.provider if first_ref else "macro_event_history",
                    bias_hint=history.bias_hint,
                )
            )
        return events

    def _persist_event_history_and_views(self, as_of_date: date, events: list[MacroEvent]) -> dict[str, int]:
        if not events:
            return {"history_count": 0, "view_count": 0}

        deduped: dict[str, MacroEvent] = {}
        for event in events:
            deduped[event.event_id] = event

        history_count = 0
        view_count = 0
        now = datetime.now(UTC)
        for event_id in sorted(deduped):
            event = deduped[event_id]
            seq = self.repository.next_event_seq(event.event_id)
            history_id = f"meh:{event.event_id}:{seq:03d}"
            source_refs = self._source_refs_from_event(event, retrieved_at=now)

            history = MacroEventHistoryDTO(
                history_id=history_id,
                event_id=event.event_id,
                event_seq=seq,
                as_of_date=as_of_date,
                event_status=self._infer_event_status(event=event, event_seq=seq),
                title=event.title,
                fact_summary=event.summary or event.title,
                theme_type=event.theme_type,
                bias_hint=event.bias_hint,
                source_refs=source_refs,
                created_at=now,
            )
            self.repository.save_event_history(history)
            history_count += 1

            view = MacroEventViewDTO(
                view_id=f"mev:{history_id}:source",
                event_id=event.event_id,
                history_id=history.history_id,
                as_of_date=as_of_date,
                view_type=MacroEventViewType.SOURCE,
                stance=self._infer_view_stance(event),
                view_text=event.summary or event.title,
                score=self._infer_view_score(event),
                score_reason="AUTO_SOURCE_VIEW",
                source_refs=source_refs,
                created_at=now,
            )
            self.repository.save_event_view(view)
            view_count += 1
        return {"history_count": history_count, "view_count": view_count}

    def _source_refs_from_event(self, event: MacroEvent, *, retrieved_at: datetime) -> list[SourceRefDTO]:
        return [
            SourceRefDTO(
                source_type=event.source_type,
                title=event.title,
                retrieved_at=retrieved_at,
                source_id=event.source_id or event.event_id,
                url=event.url,
                published_at=event.published_at,
                provider=event.provider,
            )
        ]

    def _infer_event_status(self, event: MacroEvent, event_seq: int) -> MacroEventStatus:
        text = f"{event.title}{event.summary}"
        if any(k in text for k in ["证伪", "辟谣", "失效"]):
            return MacroEventStatus.INVALIDATED
        if any(k in text for k in ["落地", "确认", "实施"]):
            return MacroEventStatus.CONFIRMED
        if any(k in text for k in ["缓和", "结束", "消退"]):
            return MacroEventStatus.RESOLVED
        if event_seq == 1:
            return MacroEventStatus.NEW
        return MacroEventStatus.DEVELOPING

    def _infer_view_stance(self, event: MacroEvent) -> MappingDirection:
        text = f"{event.title}{event.summary}"
        if any(k in text for k in ["下行", "扰动", "风险", "承压", "走弱"]):
            return MappingDirection.NEGATIVE
        if any(k in text for k in ["改善", "修复", "回升", "利好", "强化"]):
            return MappingDirection.POSITIVE
        return MappingDirection.NEUTRAL

    def _infer_view_score(self, event: MacroEvent) -> float:
        stance = self._infer_view_stance(event)
        if stance == MappingDirection.NEUTRAL:
            return 0.5
        return 0.65

    def _build_event_view_scores(self, views: list[MacroEventViewDTO]) -> dict[str, dict[str, float]]:
        by_event: dict[str, list[MacroEventViewDTO]] = defaultdict(list)
        for view in views:
            by_event[view.event_id].append(view)

        result: dict[str, dict[str, float]] = {}
        sign_map = {
            MappingDirection.POSITIVE: 1.0,
            MappingDirection.NEGATIVE: -1.0,
            MappingDirection.NEUTRAL: 0.0,
        }
        for event_id, event_views in by_event.items():
            total_weight = sum(v.score for v in event_views) or 1.0
            net = sum(sign_map[v.stance] * v.score for v in event_views) / total_weight
            result[event_id] = {
                "net": net,
                "strength": min(total_weight, 2.0),
            }
        return result

    def _average_theme_view_score(
        self,
        *,
        events: list[MacroEvent],
        view_scores: dict[str, dict[str, float]],
    ) -> float:
        if not events:
            return 0.0
        values: list[float] = []
        for event in events:
            score = view_scores.get(event.event_id)
            if score:
                values.append(abs(score["net"]))
        if not values:
            return 0.0
        return sum(values) / len(values)
