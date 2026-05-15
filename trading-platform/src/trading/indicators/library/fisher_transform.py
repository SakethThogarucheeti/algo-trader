"""Fisher Transform — non-linear normalization of price position."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class FisherTransform(Indicator):
    """
    Fisher Transform.

    Normalises the close's position within [lowest_low, highest_high] to
    [-0.999, 0.999], then applies the inverse Fisher (logit) transform:
        Fisher = 0.5 * ln((1 + x) / (1 - x))

    Extreme values (|Fisher| > 2) signal exhaustion / likely reversal.
    Returns None when fewer than *period* bars are available or when the
    high-low range is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=10, ge=2)

    alias = "fisher_transform"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        hh = float(np.max(highs))
        ll = float(np.min(lows))
        rng = hh - ll
        if rng == 0.0:
            return None

        # Midpoint normalised to [-0.999, 0.999]
        x = 2.0 * (closes[-1] - ll) / rng - 1.0
        x = max(-0.999, min(0.999, x))

        return 0.5 * math.log((1.0 + x) / (1.0 - x))

    def __repr__(self) -> str:
        return "FisherTransform()"
