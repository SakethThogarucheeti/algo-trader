"""Mean Reversion Score — composite of z-score, RSI, and Bollinger %B."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK = 3


def _rsi_scalar(closes: np.ndarray, period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(closes) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))


class MeanReversionScore(Indicator):
    """
    Mean Reversion Score — composite oscillator.

    Combines three mean-reversion signals into one normalised score:
      z_score  = (close - SMA) / std   → rescaled to [0, 100]
      rsi      = RSI(14)               → already [0, 100]
      pct_b    = Bollinger %B          → rescaled to [0, 100]

    score = (z_component + rsi_component + pct_b_component) / 3

    High score → overbought. Low score → oversold (reversal setup).
    Signal extractor: negate (low score = buy signal).

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)
        rsi_period: int = Field(default=14, ge=2)
        bb_k: float = Field(default=2.0, gt=0)

    alias = "mean_reversion_score"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        needed = max(params.period, params.rsi_period + 1) * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, needed)
        if len(rows) < max(params.period, params.rsi_period + 1):
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)

        # Z-score component
        window = closes[-params.period :]
        sma = float(np.mean(window))
        std = float(np.std(window, ddof=1))
        if std == 0:
            return None
        z = (closes[-1] - sma) / std
        z_pct = float(np.clip((z + 3) / 6 * 100, 0, 100))

        # RSI component
        rsi = _rsi_scalar(closes[-(params.rsi_period + 10) :], params.rsi_period)
        if rsi is None:
            return None

        # Bollinger %B component
        bb_upper = sma + params.bb_k * std
        bb_lower = sma - params.bb_k * std
        band_width = bb_upper - bb_lower
        if band_width == 0:
            return None
        pct_b = float((closes[-1] - bb_lower) / band_width * 100.0)
        pct_b = float(np.clip(pct_b, 0, 100))

        return float((z_pct + rsi + pct_b) / 3.0)

    def __repr__(self) -> str:
        return "MeanReversionScore()"
