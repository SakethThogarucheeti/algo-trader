"""Normalized ATR — ATR as a percentage of close price."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.true_range import true_range
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


class NormalizedATR(Indicator):
    """
    Normalized ATR.

    NormATR = ATR(period) / close * 100

    Expresses volatility as a percentage of price, making it comparable
    across symbols and different price levels over time.

    Returns float (> 0). Returns None when fewer than *period* + 1 bars
    are available or close is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=1)

    alias = "normalized_atr"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(
            self._symbol, self._interval, params.period * _LOOKBACK
        )
        if len(rows) < params.period + 1:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        tr = true_range(highs, lows, closes)
        atr = wilder_ema(tr, params.period)

        current_close = closes[-1]
        if current_close == 0.0:
            return None

        return float(atr / current_close * 100.0)

    def __repr__(self) -> str:
        return "NormalizedATR()"
