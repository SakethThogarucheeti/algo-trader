"""TrueRange — True Range as a standalone indicator (returns latest TR value)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


def true_range(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> np.ndarray:
    """
    True Range array for an OHLCV sequence.

    TR[0] = high[0] - low[0]  (no previous close)
    TR[i] = max(H-L, |H-Cprev|, |L-Cprev|)
    """
    hl = highs - lows
    prev_close = np.empty_like(closes)
    prev_close[0] = closes[0]
    prev_close[1:] = closes[:-1]
    hc = np.abs(highs - prev_close)
    lc = np.abs(lows - prev_close)
    return np.maximum(hl, np.maximum(hc, lc))


class TrueRange(Indicator):
    """
    True Range for the most recent bar.

    TR = max(H-L, |H-Cprev|, |L-Cprev|)

    Returns None when fewer than 2 bars are available (need at least one
    previous close to compute the gap components).
    """

    class Parameters(IndicatorParameters):
        pass

    alias = "true_range"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, 2)
        if len(rows) < 2:
            return None
        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)
        tr = true_range(highs, lows, closes)
        return float(tr[-1])

    def __repr__(self) -> str:
        return "TrueRange()"
