"""Donchian Channels — highest high / lowest low over N bars."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class DonchianChannels(Indicator):
    """
    Donchian Channels.

    Upper = highest high over *period* bars
    Lower = lowest low over *period* bars
    Middle = (upper + lower) / 2

    compute() returns the channel width as a fraction of mid ((upper-lower)/mid).
    Use compute_full() for (upper, middle, lower).
    Returns None when fewer than *period* bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=1)

    alias = "donchian"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        if result is None:
            return None
        upper, middle, lower = result
        return (upper - lower) / middle if middle != 0.0 else None

    async def compute_full(self, params: Parameters) -> tuple[float, float, float] | None:
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None
        upper = float(np.max([r["high"] for r in rows]))
        lower = float(np.min([r["low"] for r in rows]))
        middle = (upper + lower) / 2.0
        return upper, middle, lower

    def __repr__(self) -> str:
        return "DonchianChannels()"
