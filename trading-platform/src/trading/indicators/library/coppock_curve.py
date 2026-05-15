"""Coppock Curve — long-term momentum oscillator for swing/position bottoms."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK = 2


def _wma(values: np.ndarray) -> float:
    """Linearly weighted moving average."""
    n = len(values)
    weights = np.arange(1, n + 1, dtype=float)
    return float(np.dot(weights, values) / weights.sum())


class CoppockCurve(Indicator):
    """
    Coppock Curve.

    curve = WMA(ROC(roc1_period) + ROC(roc2_period), wma_period)

    Originally designed for monthly bars to identify major bottoms, but
    works on daily bars for swing trading. Positive and rising = buy signal.

    Returns None when insufficient bars.
    """

    class Parameters(IndicatorParameters):
        wma_period: int = Field(default=10, ge=1)
        roc1_period: int = Field(default=14, ge=1)
        roc2_period: int = Field(default=11, ge=1)

    alias = "coppock_curve"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        needed = (params.wma_period + max(params.roc1_period, params.roc2_period)) * _LOOKBACK
        rows = await self._store.fetch(self._symbol, self._interval, needed)
        total_needed = params.wma_period + max(params.roc1_period, params.roc2_period)
        if len(rows) < total_needed:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)

        # Build wma_period ROC-sum values
        roc_sums: list[float] = []
        for i in range(params.wma_period):
            idx = len(closes) - params.wma_period + i
            r1_idx = idx - params.roc1_period
            r2_idx = idx - params.roc2_period
            if r1_idx < 0 or r2_idx < 0:
                return None
            if closes[r1_idx] == 0 or closes[r2_idx] == 0:
                return None
            roc1 = (closes[idx] - closes[r1_idx]) / closes[r1_idx] * 100.0
            roc2 = (closes[idx] - closes[r2_idx]) / closes[r2_idx] * 100.0
            roc_sums.append(roc1 + roc2)

        return _wma(np.array(roc_sums))

    def __repr__(self) -> str:
        return "CoppockCurve()"
