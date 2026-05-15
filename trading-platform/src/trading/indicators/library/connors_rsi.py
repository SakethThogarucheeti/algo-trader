"""Connors RSI — composite mean-reversion oscillator."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 3


class ConnorsRSI(Indicator):
    """
    Connors RSI: average of three components.

      RSI(close, rsi_period)
    + RSI(streak_length, streak_period)
    + PercentRank(1-bar ROC, rank_period)

    streak_length: +N for N consecutive up closes, -N for down closes.
    PercentRank(x, n): fraction of last n ROC values strictly below current ROC * 100.

    Returns [0, 100]. Oversold < 10, overbought > 90.
    """

    class Parameters(IndicatorParameters):
        rsi_period: int = Field(default=3, ge=2)
        streak_period: int = Field(default=2, ge=2)
        rank_period: int = Field(default=100, ge=2)

    alias = "connors_rsi"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        limit = params.rank_period + params.rsi_period * _LOOKBACK + 1
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        min_bars = max(params.rsi_period + 1, params.streak_period + 1, params.rank_period + 1)
        if len(rows) < min_bars:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        deltas = np.diff(closes)

        # Component 1: price RSI
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = wilder_ema(gains, params.rsi_period)
        avg_loss = wilder_ema(losses, params.rsi_period)
        if avg_loss == 0.0:
            return None
        price_rsi = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)

        # Component 2: streak RSI — streak length at each bar
        streaks = np.zeros(len(closes))
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                streaks[i] = max(streaks[i - 1], 0) + 1
            elif closes[i] < closes[i - 1]:
                streaks[i] = min(streaks[i - 1], 0) - 1
            else:
                streaks[i] = 0

        streak_deltas = np.diff(streaks)
        s_gains = np.where(streak_deltas > 0, streak_deltas, 0.0)
        s_losses = np.where(streak_deltas < 0, -streak_deltas, 0.0)
        if len(s_gains) < params.streak_period + 1:
            return None
        s_avg_gain = wilder_ema(s_gains, params.streak_period)
        s_avg_loss = wilder_ema(s_losses, params.streak_period)
        if s_avg_loss == 0.0:
            streak_rsi = 100.0
        else:
            streak_rsi = 100.0 - 100.0 / (1.0 + s_avg_gain / s_avg_loss)

        # Component 3: percent rank of 1-bar ROC
        roc = deltas  # 1-bar absolute change (same ordering as pct rank)
        if len(roc) < params.rank_period + 1:
            return None
        current_roc = roc[-1]
        window_roc = roc[-(params.rank_period + 1) : -1]
        pct_rank = float(np.sum(window_roc < current_roc) / len(window_roc) * 100.0)

        return (price_rsi + streak_rsi + pct_rank) / 3.0

    def __repr__(self) -> str:
        return "ConnorsRSI()"
