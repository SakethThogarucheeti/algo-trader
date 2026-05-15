"""True Strength Index — double-smoothed momentum oscillator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 3


def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """Standard EMA (alpha = 2/(period+1)) over an array, returns full array."""
    alpha = 2.0 / (period + 1)
    out = np.empty(len(values))
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


class TSI(Indicator):
    """
    True Strength Index.

    TSI = 100 * EMA(EMA(price_change, fast), slow)
              / EMA(EMA(|price_change|, fast), slow)

    Returns [-100, 100]. Positive = bullish momentum, negative = bearish.
    Overbought > 25, oversold < -25.
    Returns None when fewer than (fast + slow) * LOOKBACK bars available.
    """

    class Parameters(IndicatorParameters):
        fast: int = Field(default=13, ge=1)
        slow: int = Field(default=25, ge=1)

    alias = "tsi"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        if params.slow <= params.fast:
            return None
        limit = (params.fast + params.slow) * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.fast + params.slow + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        pc = np.diff(closes)  # 1-bar price change
        apc = np.abs(pc)  # absolute price change

        # Double smooth
        smooth_pc = _ema(_ema(pc, params.fast), params.slow)
        smooth_apc = _ema(_ema(apc, params.fast), params.slow)

        denom = smooth_apc[-1]
        if denom == 0.0:
            return None

        return 100.0 * smooth_pc[-1] / denom

    def __repr__(self) -> str:
        return "TSI()"
