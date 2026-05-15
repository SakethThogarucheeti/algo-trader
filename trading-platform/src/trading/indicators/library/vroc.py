"""Volume Rate of Change — percentage change in volume over N bars."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class VROC(Indicator):
    """
    Volume Rate of Change.

    VROC = (volume_now - volume_N_bars_ago) / volume_N_bars_ago * 100

    Returns percentage; positive = volume expanding, negative = contracting.
    Returns None when fewer than *period* + 1 bars are available or when
    the reference bar volume is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=1)

    alias = "vroc"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None

        volumes = np.array([r["volume"] for r in rows], dtype=float)
        ref = volumes[0]
        if ref == 0.0:
            return None

        return float((volumes[-1] - ref) / ref * 100.0)

    def __repr__(self) -> str:
        return "VROC()"
