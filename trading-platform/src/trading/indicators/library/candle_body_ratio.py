"""Candle Body Ratio — body size relative to total range."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 2


class CandleBodyRatio(Indicator):
    """
    Candle Body Ratio.

    body  = |close - open|
    range = high - low
    ratio = body / range   → [0, 1]

    High ratio → conviction bar (strong move, low indecision).
    Low ratio  → doji / indecision (potential reversal).

    Returns the smoothed ratio over *period* bars so single-bar noise
    is reduced. Returns None when insufficient bars or all ranges are zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=5, ge=1)

    alias = "candle_body_ratio"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        opens  = np.array([r["open"]  for r in rows[-params.period:]], dtype=float)
        highs  = np.array([r["high"]  for r in rows[-params.period:]], dtype=float)
        lows   = np.array([r["low"]   for r in rows[-params.period:]], dtype=float)
        closes = np.array([r["close"] for r in rows[-params.period:]], dtype=float)

        ranges = highs - lows
        bodies = np.abs(closes - opens)
        valid = ranges > 0
        if not np.any(valid):
            return None
        return float(np.mean(bodies[valid] / ranges[valid]))

    def __repr__(self) -> str:
        return "CandleBodyRatio()"
