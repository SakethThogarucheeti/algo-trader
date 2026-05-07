"""Supertrend — trend-following indicator based on ATR bands."""

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


class Supertrend(Indicator):
    """
    Supertrend indicator.

    Basic upper band = (H+L)/2 + multiplier * ATR
    Basic lower band = (H+L)/2 - multiplier * ATR

    The final band flips direction when price crosses the opposite band.
    compute() returns +1.0 (uptrend) or -1.0 (downtrend).
    Use compute_full() for (direction, supertrend_level).
    Returns None when insufficient data.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=10, ge=1)
        multiplier: float = Field(default=3.0, gt=0)

    alias = "supertrend"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[0] if result is not None else None

    async def compute_full(self, params: Parameters) -> tuple[float, float] | None:
        limit = params.period * _LOOKBACK_FACTOR
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.period + 1:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        tr = true_range(highs, lows, closes)
        n = len(rows)

        # Compute ATR for each bar via rolling Wilder EMA
        atrs = np.zeros(n)
        for i in range(params.period - 1, n):
            atrs[i] = wilder_ema(tr[max(0, i - params.period * 3 + 1) : i + 1], params.period)

        hl2 = (highs + lows) / 2.0
        basic_upper = hl2 + params.multiplier * atrs
        basic_lower = hl2 - params.multiplier * atrs

        # Walk forward: flip bands based on price
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        direction = np.ones(n)  # +1 uptrend, -1 downtrend

        for i in range(1, n):
            final_lower[i] = (
                max(basic_lower[i], final_lower[i - 1])
                if closes[i - 1] > final_lower[i - 1]
                else basic_lower[i]
            )
            final_upper[i] = (
                min(basic_upper[i], final_upper[i - 1])
                if closes[i - 1] < final_upper[i - 1]
                else basic_upper[i]
            )

            if closes[i] > final_upper[i - 1]:
                direction[i] = 1.0
            elif closes[i] < final_lower[i - 1]:
                direction[i] = -1.0
            else:
                direction[i] = direction[i - 1]

        dir_now = direction[-1]
        level = final_lower[-1] if dir_now == 1.0 else final_upper[-1]
        return float(dir_now), float(level)

    def __repr__(self) -> str:
        return "Supertrend()"
