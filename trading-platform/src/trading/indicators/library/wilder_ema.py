"""WilderEMA — Wilder's exponential moving average as a standalone indicator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field
from scipy.signal import lfilter  # type: ignore[import-untyped]

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK_FACTOR = 3


def wilder_ema(values: np.ndarray, period: int) -> float:
    """
    Wilder's EMA (alpha = 1/period) over ``values``.

    Equivalent to Polars ewm_mean(alpha=1/period, adjust=False)[-1].
    Uses scipy.signal.lfilter for a single vectorised pass.
    """
    alpha = 1.0 / period
    b = [alpha]
    a = [1.0, -(1.0 - alpha)]
    zi = np.array([values[0] * (1.0 - alpha)])
    out, _ = lfilter(b, a, values, zi=zi)
    return float(out[-1])


class WilderEMA(Indicator):
    """
    Wilder's EMA (alpha = 1/period) applied to the close price.

    Distinct from the standard EMA in that alpha = 1/period rather than
    2/(period+1). Used internally by RSI and ATR; also useful directly
    when you want the same smoothing characteristic as those indicators.

    Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=1)

    alias = "wilder_ema"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(
            self._symbol, self._interval, params.period * _LOOKBACK_FACTOR
        )
        if len(rows) < params.period:
            return None
        closes = np.array([r["close"] for r in rows], dtype=float)
        return wilder_ema(closes, params.period)

    def __repr__(self) -> str:
        return "WilderEMA()"
