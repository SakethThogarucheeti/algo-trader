"""Aroon Oscillator — measures recency of highs vs lows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 2


class Aroon(Indicator):
    """
    Aroon Oscillator.

    aroon_up   = (period - bars_since_high) / period * 100
    aroon_down = (period - bars_since_low)  / period * 100
    oscillator = aroon_up - aroon_down

    Range [-100, 100].
    Negative (recent lows) → oversold swing setup → mean reversion up.

    Signal extractor: negate (negative oscillator = potential reversal up).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=25, ge=2)

    alias = "aroon"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(
            self._symbol, self._interval, (params.period + 1) * _LOOKBACK
        )
        if len(rows) < params.period + 1:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)

        window_h = highs[-(params.period + 1) :]
        window_l = lows[-(params.period + 1) :]

        bars_since_high = params.period - int(np.argmax(window_h))
        bars_since_low = params.period - int(np.argmin(window_l))

        aroon_up = (params.period - bars_since_high) / params.period * 100.0
        aroon_down = (params.period - bars_since_low) / params.period * 100.0
        return float(aroon_up - aroon_down)

    def __repr__(self) -> str:
        return "Aroon()"
