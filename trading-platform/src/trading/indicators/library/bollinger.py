"""Bollinger Bands — SMA ± k standard deviations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class BollingerBands(Indicator):
    """
    Bollinger Bands: middle = SMA(period), upper/lower = middle ± k*stdev.

    compute() returns the %B value: where the current close sits within the
    bands (0 = lower band, 1 = upper band, >1 above, <0 below).

    Use compute_full() for (upper, middle, lower, bandwidth, percent_b).
    Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)
        k: float = Field(default=2.0, gt=0)

    alias = "bollinger"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[4] if result is not None else None  # percent_b

    async def compute_full(
        self, params: Parameters
    ) -> tuple[float, float, float, float, float] | None:
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        middle = float(np.mean(closes))
        std = float(np.std(closes, ddof=1))
        upper = middle + params.k * std
        lower = middle - params.k * std
        bandwidth = (upper - lower) / middle if middle != 0.0 else 0.0
        current = closes[-1]
        band_width = upper - lower
        percent_b = (current - lower) / band_width if band_width != 0.0 else 0.5
        return upper, middle, lower, bandwidth, percent_b

    def __repr__(self) -> str:
        return "BollingerBands()"
