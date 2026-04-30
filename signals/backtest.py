from __future__ import annotations

from typing import Protocol

from contracts.signals_contracts import BacktestResultDTO, SignalRunRequestDTO


class BacktestEngine(Protocol):
    """Reserved interface for future portfolio backtesting integration."""

    def run(self, request: SignalRunRequestDTO) -> BacktestResultDTO:
        ...
