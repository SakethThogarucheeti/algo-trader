"""Chaikin Money Flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class CMF(Indicator):
    """
    Chaikin Money Flow.

    Money Flow Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
    Money Flow Volume = MFM * Volume
    CMF = sum(MFV, period) / sum(Volume, period)

    Range: -1 to +1. Positive = buying pressure, negative = selling pressure.
    Returns None when fewer than *period* bars or total volume is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=1)

    alias = "cmf"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)
        volumes = np.array([r["volume"] for r in rows], dtype=float)

        hl_range = highs - lows
        # When H == L (no movement), MFM = 0
        mfm = np.where(hl_range != 0.0, ((closes - lows) - (highs - closes)) / hl_range, 0.0)
        mfv = mfm * volumes

        total_vol = volumes.sum()
        if total_vol == 0.0:
            return None
        return float(mfv.sum() / total_vol)

    def __repr__(self) -> str:
        return "CMF()"
