"""Price vs 52-week High — how far price has fallen from its peak."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 1


class PriceVs52wHigh(Indicator):
    """
    Price vs N-bar High.

    (close - highest_high(period)) / highest_high(period) * 100

    Always <= 0. The more negative, the further price has fallen from peak.
    Deep negative = mean reversion anchor (price far from 52w high).

    Signal extractor: negate (more negative = more oversold = higher signal).

    Returns None when insufficient bars or high is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=252, ge=2)

    alias = "price_vs_52w_high"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        highs  = np.array([r["high"]  for r in rows[-params.period:]], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        peak = float(np.max(highs))
        if peak == 0:
            return None
        return float((closes[-1] - peak) / peak * 100.0)

    def __repr__(self) -> str:
        return "PriceVs52wHigh()"
