"""Relative Volume — current volume relative to its rolling average."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class RVOL(Indicator):
    """
    Relative Volume.

    RVOL = volume / SMA(volume, period)

    Returns ratio; > 1 = above-average volume, > 2 = significant spike.
    Returns None when fewer than *period* bars are available or avg volume
    is zero (no trading activity in window).
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)

    alias = "rvol"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period:
            return None

        volumes = np.array([r["volume"] for r in rows], dtype=float)
        avg_vol = float(np.mean(volumes[:-1]))  # average over prior period bars
        if avg_vol == 0.0:
            return None

        return float(volumes[-1] / avg_vol)

    def __repr__(self) -> str:
        return "RVOL()"
