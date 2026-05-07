"""RSI Divergence — bullish when price makes new low but RSI does not."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


def _rsi_series(closes: np.ndarray, period: int) -> np.ndarray:
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


class RSIDivergence(Indicator):
    """
    RSI Divergence score.

    Measures the difference between the normalised price change and
    the normalised RSI change over a lookback window:

        price_chg  = (close_now - close_N_ago) / close_N_ago
        rsi_chg    = (rsi_now  - rsi_N_ago)  / 100
        divergence = rsi_chg - price_chg

    Positive value → bullish divergence (RSI stronger than price → mean reversion up).
    Negative value → bearish divergence.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        rsi_period: int = Field(default=14, ge=2)
        divergence_window: int = Field(default=10, ge=2)

    alias = "rsi_divergence"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        needed = (params.rsi_period + params.divergence_window) * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, needed)
        if len(rows) < params.rsi_period + params.divergence_window + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        rsi = _rsi_series(closes, params.rsi_period)

        # Need at least divergence_window valid RSI values
        valid_idx = np.where(~np.isnan(rsi))[0]
        if len(valid_idx) < params.divergence_window:
            return None

        now_idx = valid_idx[-1]
        ago_idx = valid_idx[-params.divergence_window]

        close_now = closes[now_idx]
        close_ago = closes[ago_idx]
        if close_ago == 0:
            return None

        price_chg = (close_now - close_ago) / close_ago
        rsi_chg = (rsi[now_idx] - rsi[ago_idx]) / 100.0

        return float(rsi_chg - price_chg)

    def __repr__(self) -> str:
        return "RSIDivergence()"
