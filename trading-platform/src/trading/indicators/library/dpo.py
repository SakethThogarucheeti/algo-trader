"""Detrended Price Oscillator — removes dominant trend to expose cycles."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class DPO(Indicator):
    """
    Detrended Price Oscillator.

    DPO = close - SMA(close, period) shifted back (period // 2 + 1) bars.

    The shift removes the trend component, leaving oscillations around
    the mid-cycle average. Positive = above detrended mean (overbought),
    Negative = below (oversold).

    Returns None when fewer than *period* + shift bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)

    alias = "dpo"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        shift = params.period // 2 + 1
        limit = params.period + shift
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < limit:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)

        # SMA of the window ending at bar (limit - shift - 1)
        sma_window = closes[: params.period]
        sma = float(np.mean(sma_window))

        # Current close is the last bar
        current_close = closes[-1]
        return current_close - sma

    def __repr__(self) -> str:
        return "DPO()"
