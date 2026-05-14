"""Elder Ray — Bull/Bear Power relative to EMA."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


def _ema(values: np.ndarray, period: int) -> float:
    alpha = 2.0 / (period + 1)
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1.0 - alpha) * acc
    return acc


class ElderRay(Indicator):
    """
    Elder Ray Index — Bull Power and Bear Power combined.

    bull_power = high - EMA(close, period)
    bear_power = low  - EMA(close, period)
    elder_ray  = bull_power + bear_power  (net power)

    Positive → price action above EMA (bullish context).
    Negative → price action below EMA (bearish context, mean reversion up).

    Signal extractor: negate (negative elder_ray = oversold stretch → reversal).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=13, ge=2)

    alias = "elder_ray"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        ema = _ema(closes, params.period)
        bull_power = highs[-1] - ema
        bear_power = lows[-1] - ema
        return float(bull_power + bear_power)

    def __repr__(self) -> str:
        return "ElderRay()"
