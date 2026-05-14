"""Price Percentile — where current close sits within its N-bar distribution."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 2


class PricePercentile(Indicator):
    """
    Price Percentile.

    Fraction of the last *period* closes that are below the current close,
    expressed as [0, 100].

    0  → current close is the lowest in the window (oversold)
    100 → current close is the highest (overbought)

    More robust than Bollinger %B — makes no Gaussian assumption.
    Signal extractor: negate (low percentile = oversold → reversal up).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=50, ge=2)

    alias = "price_percentile"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        closes = np.array([r["close"] for r in rows[-params.period :]], dtype=float)
        current = closes[-1]
        pct = float(np.sum(closes[:-1] < current) / (params.period - 1) * 100.0)
        return pct

    def __repr__(self) -> str:
        return "PricePercentile()"
