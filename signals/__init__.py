from __future__ import annotations

from signals.plugins.custom_python_signal import CustomPythonSignalPlugin
from signals.plugins.liquidity_concentration import LiquidityConcentrationPlugin
from signals.plugins.market_breadth_crowding import MarketBreadthCrowdingPlugin
from signals.plugins.registry import SignalRegistry


def default_signal_registry() -> SignalRegistry:
    return SignalRegistry(
        plugins=[
            CustomPythonSignalPlugin(),
            LiquidityConcentrationPlugin(),
            MarketBreadthCrowdingPlugin(),
        ]
    )
