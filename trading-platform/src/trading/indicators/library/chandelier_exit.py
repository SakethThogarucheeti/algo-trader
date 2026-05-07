"""Chandelier Exit — ATR-based measure of how extended price is from recent high."""

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


class ChandelierExit(Indicator):
    """
    Chandelier Exit distance.

    chandelier_long  = highest_high(period) - ATR(period) * multiplier
    distance         = (close - chandelier_long) / close * 100

    Positive → price well above the exit line (not stretched down).
    Negative → price has fallen below the chandelier (oversold, stretched).

    Signal extractor: negate (negative = price below chandelier = buy setup).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=22, ge=2)
        multiplier: float = Field(default=3.0, gt=0)

    alias = "chandelier_exit"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period + 1:
            return None

        highs  = np.array([r["high"]  for r in rows], dtype=float)
        lows   = np.array([r["low"]   for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        tr = true_range(highs, lows, closes)
        atr = wilder_ema(tr[-params.period:], params.period)
        highest_high = float(np.max(highs[-params.period:]))
        chandelier = highest_high - atr * params.multiplier

        current_close = closes[-1]
        if current_close == 0:
            return None
        return float((current_close - chandelier) / current_close * 100.0)

    def __repr__(self) -> str:
        return "ChandelierExit()"
