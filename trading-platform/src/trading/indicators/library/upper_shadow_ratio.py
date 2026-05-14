"""Upper Shadow Ratio — rejection of highs, bearish wick signal."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 2


class UpperShadowRatio(Indicator):
    """
    Upper Shadow Ratio.

    upper_shadow = high - max(open, close)
    ratio        = upper_shadow / (high - low)   → [0, 1]

    High ratio → strong rejection at the top (bearish wick).
    Smoothed over *period* bars. High reading = overhead resistance = reversal down.

    Signal extractor: negate (high upper shadow → overbought rejection → sell).

    Returns None when insufficient bars or all ranges are zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=5, ge=1)

    alias = "upper_shadow_ratio"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        opens = np.array([r["open"] for r in rows[-params.period :]], dtype=float)
        highs = np.array([r["high"] for r in rows[-params.period :]], dtype=float)
        lows = np.array([r["low"] for r in rows[-params.period :]], dtype=float)
        closes = np.array([r["close"] for r in rows[-params.period :]], dtype=float)

        ranges = highs - lows
        upper_shadows = highs - np.maximum(opens, closes)
        valid = ranges > 0
        if not np.any(valid):
            return None
        return float(np.mean(upper_shadows[valid] / ranges[valid]))

    def __repr__(self) -> str:
        return "UpperShadowRatio()"
