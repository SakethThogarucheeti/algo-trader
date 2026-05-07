"""Linear Regression Slope — trend strength without lag."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 2


class LinearRegressionSlope(Indicator):
    """
    Linear Regression Slope.

    Fits a least-squares line to the last *period* closes and returns
    the slope normalised by the mean price (so it's comparable across symbols):

        slope_pct = slope / mean(closes) * 100

    Positive → uptrend. Negative → downtrend.
    Signal extractor: as-is for trend, negate for mean reversion.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=3)

    alias = "linreg_slope"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period * _LOOKBACK)
        if len(rows) < params.period:
            return None

        closes = np.array([r["close"] for r in rows[-params.period:]], dtype=float)
        x = np.arange(params.period, dtype=float)
        x -= x.mean()
        slope = float(np.dot(x, closes) / np.dot(x, x))
        mean_price = float(np.mean(closes))
        if mean_price == 0:
            return None
        return float(slope / mean_price * 100.0)

    def __repr__(self) -> str:
        return "LinearRegressionSlope()"
