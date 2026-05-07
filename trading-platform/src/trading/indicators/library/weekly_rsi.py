"""Weekly RSI Proxy — RSI computed on 5-bar rolled closes (daily → weekly)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


class WeeklyRSI(Indicator):
    """
    Weekly RSI Proxy.

    Computes RSI on weekly closes synthesised from daily bars by sampling
    every *week_bars* bars (default 5 = 1 trading week). This approximates
    the weekly RSI without needing a separate weekly data feed.

    Useful for daily-bar swing trading — the weekly RSI filters out
    short-term noise and gives the higher-timeframe mean-reversion context.

    Signal extractor: negate (100 - weekly_rsi) for mean reversion.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        rsi_period: int = Field(default=14, ge=2)
        week_bars: int = Field(default=5, ge=1)

    alias = "weekly_rsi"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        needed = (params.rsi_period + 1) * params.week_bars * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, needed)

        closes = np.array([r["close"] for r in rows], dtype=float)
        # Sample weekly closes (last bar of each week window)
        weekly = closes[params.week_bars - 1::params.week_bars]
        if len(weekly) < params.rsi_period + 1:
            return None

        deltas = np.diff(weekly)
        gains  = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = float(np.mean(gains[:params.rsi_period]))
        avg_loss = float(np.mean(losses[:params.rsi_period]))
        for i in range(params.rsi_period, len(weekly) - 1):
            avg_gain = (avg_gain * (params.rsi_period - 1) + gains[i]) / params.rsi_period
            avg_loss = (avg_loss * (params.rsi_period - 1) + losses[i]) / params.rsi_period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100.0 - 100.0 / (1.0 + rs))

    def __repr__(self) -> str:
        return "WeeklyRSI()"
