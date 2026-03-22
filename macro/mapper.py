from __future__ import annotations

from dataclasses import dataclass

from contracts.enums import MacroBiasTag, MappingDirection
from contracts.macro_contracts import MacroIndustryMappingDTO, MacroThemeCardSummaryDTO


@dataclass(frozen=True)
class _IndustrySeed:
    sw_l1_id: str
    sw_l1_name: str
    score: float
    reason: str


class MacroIndustryMapper:
    _BIAS_SEEDS: dict[MacroBiasTag, tuple[_IndustrySeed, ...]] = {
        MacroBiasTag.LIQUIDITY_DOMINANT: (
            _IndustrySeed("801780", "银行", 1.2, "流动性改善有利估值修复"),
            _IndustrySeed("801790", "非银金融", 1.1, "流动性环境改善支撑风险资产"),
            _IndustrySeed("801050", "有色金属", 0.8, "流动性宽松常见顺周期修复"),
        ),
        MacroBiasTag.POLICY_EXPECTATION_DOMINANT: (
            _IndustrySeed("801740", "国防军工", 0.9, "政策预期提升主题活跃度"),
            _IndustrySeed("801710", "建筑材料", 0.7, "政策发力对基建链条有支撑"),
            _IndustrySeed("801020", "采掘", -0.5, "政策不确定阶段对高波动板块有压制"),
        ),
        MacroBiasTag.FUNDAMENTAL_VALIDATION_DOMINANT: (
            _IndustrySeed("801120", "食品饮料", 0.8, "盈利验证提升基本面定价权重"),
            _IndustrySeed("801150", "医药生物", 0.6, "业绩确定性受益于验证环境"),
            _IndustrySeed("801750", "计算机", -0.6, "高预期板块面临业绩验证压力"),
        ),
        MacroBiasTag.RISK_APPETITE_RECOVERY: (
            _IndustrySeed("801750", "计算机", 1.1, "风险偏好修复利好成长弹性"),
            _IndustrySeed("801760", "传媒", 0.9, "主题与成长交易敏感度高"),
            _IndustrySeed("801200", "商业贸易", 0.4, "消费链风险偏好回暖"),
        ),
        MacroBiasTag.EXTERNAL_DISTURBANCE_DOMINANT: (
            _IndustrySeed("801120", "食品饮料", 0.5, "外部扰动阶段防御属性更占优"),
            _IndustrySeed("801140", "轻工制造", -0.7, "外需不确定性压制出口链"),
            _IndustrySeed("801080", "电子", -0.8, "海外扰动提高科技链波动"),
        ),
        MacroBiasTag.DEFENSIVE_PREFERENCE_RISING: (
            _IndustrySeed("801120", "食品饮料", 0.9, "防御偏好阶段资金偏好稳定现金流"),
            _IndustrySeed("801150", "医药生物", 0.9, "防御属性和业绩韧性受青睐"),
            _IndustrySeed("801010", "农林牧渔", 0.5, "低估值与防御逻辑增强"),
        ),
        MacroBiasTag.PRO_CYCLICAL_TRADING_WARMING: (
            _IndustrySeed("801050", "有色金属", 1.0, "顺周期交易升温"),
            _IndustrySeed("801040", "钢铁", 0.9, "周期弹性提升"),
            _IndustrySeed("801790", "非银金融", 0.6, "交易活跃度提升利好券商链"),
        ),
        MacroBiasTag.THEMATIC_RISK_APPETITE_DOMINANT: (
            _IndustrySeed("801750", "计算机", 1.0, "主题交易偏好提升"),
            _IndustrySeed("801080", "电子", 0.7, "主题扩散至科技链"),
            _IndustrySeed("801760", "传媒", 0.8, "主题活跃度提升"),
        ),
    }

    def map_to_sw_l1(
        self,
        biases: list[MacroBiasTag],
        theme_cards: list[MacroThemeCardSummaryDTO],
    ) -> list[MacroIndustryMappingDTO]:
        score_board: dict[str, dict[str, float | str | list[str]]] = {}

        for rank, bias in enumerate(biases):
            rank_weight = max(1.0 - rank * 0.2, 0.6)
            for seed in self._BIAS_SEEDS.get(bias, ()):
                bucket = score_board.setdefault(
                    seed.sw_l1_id,
                    {
                        "sw_l1_name": seed.sw_l1_name,
                        "score": 0.0,
                        "reasons": [],
                    },
                )
                bucket["score"] = float(bucket["score"]) + seed.score * rank_weight
                cast_reasons = bucket["reasons"]
                assert isinstance(cast_reasons, list)
                cast_reasons.append(f"{bias.value}:{seed.reason}")

        for card in theme_cards:
            for sector_label in card.sw_l1_positive:
                for sw_l1_id, value in score_board.items():
                    if value["sw_l1_name"] == sector_label or sw_l1_id == sector_label:
                        value["score"] = float(value["score"]) + 0.5
            for sector_label in card.sw_l1_negative:
                for sw_l1_id, value in score_board.items():
                    if value["sw_l1_name"] == sector_label or sw_l1_id == sector_label:
                        value["score"] = float(value["score"]) - 0.5

        mappings: list[MacroIndustryMappingDTO] = []
        for sw_l1_id, payload in score_board.items():
            score = float(payload["score"])
            if score >= 0.6:
                direction = MappingDirection.POSITIVE
            elif score <= -0.6:
                direction = MappingDirection.NEGATIVE
            else:
                direction = MappingDirection.NEUTRAL

            reasons = payload["reasons"]
            assert isinstance(reasons, list)
            reason = "；".join(reasons[:2]) if reasons else "规则映射未给出强信号"

            mappings.append(
                MacroIndustryMappingDTO(
                    sw_l1_id=sw_l1_id,
                    sw_l1_name=str(payload["sw_l1_name"]),
                    direction=direction,
                    score=round(score, 3),
                    reason=reason,
                )
            )

        mappings.sort(key=lambda x: (x.direction.value, -(x.score or 0.0), x.sw_l1_id))
        return mappings
