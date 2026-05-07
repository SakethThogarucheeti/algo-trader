"""Keltner Channels — EMA ± k * ATR."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.true_range import true_range
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK_FACTOR = 3


class KeltnerChannels(Indicator):
    """
    Keltner Channels.

    Middle = EMA(close, ema_period)   [standard alpha = 2/(n+1)]
    Upper  = Middle + k * ATR(atr_period)
    Lower  = Middle - k * ATR(atr_period)

    compute() returns channel width as a fraction of middle ((upper-lower)/middle).
    Use compute_full() for (upper, middle, lower).
    Returns None when insufficient data or ATR is zero.
    """

    class Parameters(IndicatorParameters):
        ema_period: int = Field(default=20, ge=1)
        atr_period: int = Field(default=10, ge=1)
        k: float = Field(default=2.0, gt=0)

    alias = "keltner"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        if result is None:
            return None
        upper, middle, lower = result
        return (upper - lower) / middle if middle != 0.0 else None

    async def compute_full(self, params: Parameters) -> tuple[float, float, float] | None:
        period = max(params.ema_period, params.atr_period)
        rows = await self._store.fetch(self._symbol, self._interval, period * _LOOKBACK_FACTOR)
        if len(rows) < period:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)

        # Standard EMA (alpha = 2/(n+1))
        alpha = 2.0 / (params.ema_period + 1)
        acc = closes[0]
        for c in closes[1:]:
            acc = alpha * c + (1.0 - alpha) * acc
        middle = acc

        tr = true_range(highs, lows, closes)
        atr = wilder_ema(tr, params.atr_period)
        if atr <= 0.0:
            return None

        upper = middle + params.k * atr
        lower = middle - params.k * atr
        return upper, middle, lower

    def __repr__(self) -> str:
        return "KeltnerChannels()"
