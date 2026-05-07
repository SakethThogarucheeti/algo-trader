"""Relative Strength Index (Wilder smoothing)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK_FACTOR = 3


class RSI(Indicator):
    """
    RSI using Wilder smoothing (alpha = 1/period).

    Consistent with the existing TechnicalFeatureEngine implementation:
    - Returns None when avg_loss == 0 (flat or purely up market — RSI is
      undefined rather than 100, preventing false overbought signals).
    - Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=2)

    alias = "rsi"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(
            self._symbol, self._interval, params.period * _LOOKBACK_FACTOR
        )
        if len(rows) < params.period + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = wilder_ema(gains, params.period)
        avg_loss = wilder_ema(losses, params.period)

        if avg_loss == 0.0:
            return None  # undefined — flat or one-sided uptrend

        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def __repr__(self) -> str:
        return "RSI()"
