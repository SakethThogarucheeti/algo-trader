"""Williams %R."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class WilliamsR(Indicator):
    """
    Williams %R.

    %R = -100 * (highest_high - close) / (highest_high - lowest_low)

    Range: -100 (oversold) to 0 (overbought).
    Returns None when fewer than *period* bars are available or range is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=1)

    alias = "williams_r"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        close = rows[-1]["close"]

        hh = float(np.max(highs))
        ll = float(np.min(lows))
        rng = hh - ll
        if rng == 0.0:
            return None
        return -100.0 * (hh - close) / rng

    def __repr__(self) -> str:
        return "WilliamsR()"
