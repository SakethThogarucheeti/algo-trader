"""Simple Moving Average."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class SMA(Indicator):
    """
    Arithmetic mean of the last *period* closing prices.

    Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=1)

    alias = "sma"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None
        closes = np.array([r["close"] for r in rows], dtype=float)
        return float(np.mean(closes))

    def __repr__(self) -> str:
        return "SMA()"
