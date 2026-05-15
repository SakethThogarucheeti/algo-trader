"""Stochastic RSI — RSI normalised within its own N-bar range."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 3


def _rsi_series(closes: np.ndarray, period: int) -> np.ndarray:
    """Return RSI value at each bar (nan until warmed up)."""
    n = len(closes)
    rsi = np.full(n, np.nan)
    if n < period + 1:
        return rsi
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


class StochasticRSI(Indicator):
    """
    Stochastic RSI.

    StochRSI = (RSI - min(RSI, period)) / (max(RSI, period) - min(RSI, period))

    Ranges [0, 100]. More sensitive than plain RSI — useful for picking
    intraday and swing exhaustion points earlier.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        rsi_period: int = Field(default=14, ge=2)
        stoch_period: int = Field(default=14, ge=2)

    alias = "stochastic_rsi"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        needed = (params.rsi_period + params.stoch_period) * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, needed)
        if len(rows) < params.rsi_period + params.stoch_period + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        rsi = _rsi_series(closes, params.rsi_period)
        valid = rsi[~np.isnan(rsi)]
        if len(valid) < params.stoch_period:
            return None

        window = valid[-params.stoch_period :]
        lo, hi = float(np.min(window)), float(np.max(window))
        if hi == lo:
            return None
        return float((valid[-1] - lo) / (hi - lo) * 100.0)

    def __repr__(self) -> str:
        return "StochasticRSI()"
