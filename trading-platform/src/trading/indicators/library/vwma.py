"""Volume-Weighted Moving Average."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class VWMA(Indicator):
    """
    Volume-Weighted Moving Average.

    VWMA = sum(close * volume, period) / sum(volume, period)

    Like SMA but bars with higher volume carry more weight.
    Returns None when fewer than *period* bars or total volume is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=1)

    alias = "vwma"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        volumes = np.array([r["volume"] for r in rows], dtype=float)

        total_vol = volumes.sum()
        if total_vol == 0.0:
            return None
        return float((closes * volumes).sum() / total_vol)

    def __repr__(self) -> str:
        return "VWMA()"
