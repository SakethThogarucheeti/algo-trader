"""Distance from Moving Average — normalised rubber-band stretch."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 2


class DistanceFromMA(Indicator):
    """
    Distance from Moving Average.

    (close - SMA(period)) / SMA(period) * 100

    Positive → price stretched above MA (overbought).
    Negative → price stretched below MA (oversold → reversal up).

    Signal extractor: negate (negative = oversold stretch → buy).

    Returns None when insufficient bars or SMA is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)

    alias = "distance_from_ma"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        sma = float(np.mean(closes[-params.period:]))
        if sma == 0:
            return None
        return float((closes[-1] - sma) / sma * 100.0)

    def __repr__(self) -> str:
        return "DistanceFromMA()"
