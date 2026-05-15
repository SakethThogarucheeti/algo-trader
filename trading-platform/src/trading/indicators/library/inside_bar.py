"""Inside Bar — coiling / compression before a swing move."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 2


class InsideBar(Indicator):
    """
    Inside Bar ratio.

    An inside bar is one where high < prev_high and low > prev_low —
    the bar is completely contained within the previous bar's range.

    Returns the fraction of the last *period* bars that are inside bars,
    as a value in [0, 1]. High reading = compression / coiling.

    Not directly a directional signal — combine with RSI direction.
    As-is: high value = compressed volatility (often precedes breakout).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=10, ge=2)

    alias = "inside_bar"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(
            self._symbol, self._interval, (params.period + 1) * _LOOKBACK
        )
        if len(rows) < params.period + 1:
            return None

        highs = np.array([r["high"] for r in rows[-(params.period + 1) :]], dtype=float)
        lows = np.array([r["low"] for r in rows[-(params.period + 1) :]], dtype=float)

        count = 0
        for i in range(1, params.period + 1):
            if highs[i] < highs[i - 1] and lows[i] > lows[i - 1]:
                count += 1
        return float(count / params.period)

    def __repr__(self) -> str:
        return "InsideBar()"
