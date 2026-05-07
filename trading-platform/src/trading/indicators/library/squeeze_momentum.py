"""Squeeze Momentum — Bollinger/Keltner compression + momentum signal."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.true_range import true_range
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


def _ema_scalar(values: np.ndarray, period: int) -> float:
    """Standard EMA, returns final value only."""
    alpha = 2.0 / (period + 1)
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1.0 - alpha) * acc
    return acc


class SqueezeMomentum(Indicator):
    """
    Squeeze Momentum (LazyBear / John Carter approach).

    squeeze_on  = True when Bollinger Bands are inside Keltner Channels
                  (compressed volatility / coiling)

    momentum    = linear regression of delta, where:
                  delta = close - midpoint of (HH+LL)/2 and SMA(close)
                  over *period* bars

    Returns the momentum value (positive = up, negative = down) when a
    squeeze has recently fired, and the raw momentum otherwise. The sign
    flip on output is left to the signal extractor in the test.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=4)
        bb_k: float = Field(default=2.0, gt=0)
        kc_k: float = Field(default=1.5, gt=0)

    alias = "squeeze_momentum"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        limit = params.period * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        # Bollinger Bands over last period bars
        window_c = closes[-params.period :]
        sma = float(np.mean(window_c))
        std = float(np.std(window_c, ddof=1))
        bb_upper = sma + params.bb_k * std
        bb_lower = sma - params.bb_k * std

        # Keltner Channels
        tr = true_range(highs, lows, closes)
        atr = wilder_ema(tr[-params.period :], params.period)
        kc_upper = sma + params.kc_k * atr
        kc_lower = sma - params.kc_k * atr

        # Momentum: linear regression value of delta
        hh = float(np.max(highs[-params.period :]))
        ll = float(np.min(lows[-params.period :]))
        midpoint = (hh + ll) / 2.0 + sma
        midpoint /= 2.0

        delta = closes[-params.period :] - midpoint

        # Linear regression of delta (value at last bar)
        x = np.arange(params.period, dtype=float)
        x -= x.mean()
        slope = float(np.dot(x, delta) / np.dot(x, x))
        intercept = float(np.mean(delta))
        momentum = slope * (params.period - 1) / 2.0 + intercept

        return momentum

    def __repr__(self) -> str:
        return "SqueezeMomentum()"
