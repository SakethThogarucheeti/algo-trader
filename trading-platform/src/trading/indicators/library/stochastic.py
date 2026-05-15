"""Stochastic Oscillator — %K and %D."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class Stochastic(Indicator):
    """
    Stochastic Oscillator.

    %K = 100 * (close - lowest_low) / (highest_high - lowest_low)
    %D = SMA(%K, d_period)

    compute() returns %K. Use compute_full() for (%K, %D).
    Returns None when fewer than *k_period* bars are available or when
    highest_high == lowest_low (no price movement).
    """

    class Parameters(IndicatorParameters):
        k_period: int = Field(default=14, ge=1)
        d_period: int = Field(default=3, ge=1)

    alias = "stochastic"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[0] if result is not None else None

    async def compute_full(self, params: Parameters) -> tuple[float, float] | None:
        # Need k_period + d_period - 1 bars to compute d_period %K values for %D
        limit = params.k_period + params.d_period - 1
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.k_period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        # Compute %K for each bar in the trailing window (for %D smoothing)
        k_values: list[float] = []
        for i in range(params.k_period - 1, len(rows)):
            window_h = highs[i - params.k_period + 1 : i + 1]
            window_l = lows[i - params.k_period + 1 : i + 1]
            hh = float(np.max(window_h))
            ll = float(np.min(window_l))
            rng = hh - ll
            if rng == 0.0:
                k_values.append(50.0)  # mid-point when flat
            else:
                k_values.append(100.0 * (closes[i] - ll) / rng)

        k = k_values[-1]
        d = float(np.mean(k_values[-params.d_period :])) if len(k_values) >= params.d_period else k
        return k, d

    def __repr__(self) -> str:
        return "Stochastic()"
