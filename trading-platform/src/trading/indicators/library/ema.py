"""Exponential Moving Average (Wilder smoothing)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

# Fetch 3× the period so the EWM seed bias has decayed to negligible levels
# before the value we return. This matches the warmup approach used by the
# existing TechnicalFeatureEngine.
_LOOKBACK_FACTOR = 3


class EMA(Indicator):
    """
    Wilder EMA with configurable period.

    alpha = 1 / period  (consistent with TechnicalFeatureEngine and Polars
    ewm_mean(span=period, adjust=False)).

    Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=9, ge=1)

    alias = "ema"

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
        return "EMA()"
