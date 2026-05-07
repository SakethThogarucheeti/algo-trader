"""Chaikin Volatility — rate of change in the EMA of H-L spread."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_LOOKBACK_FACTOR = 3


class ChaikinVolatility(Indicator):
    """
    Chaikin Volatility.

    EMA of (High - Low) over *ema_period* bars.
    CV = 100 * (EMA_now - EMA[roc_period ago]) / EMA[roc_period ago]

    Rising CV → expanding volatility; falling → contracting.
    Returns None when insufficient data or the reference EMA is zero.
    """

    class Parameters(IndicatorParameters):
        ema_period: int = Field(default=10, ge=1)
        roc_period: int = Field(default=10, ge=1)

    alias = "chaikin_vol"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        limit = (params.ema_period + params.roc_period) * _LOOKBACK_FACTOR
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.ema_period + params.roc_period:
            return None

        hl = np.array([r["high"] - r["low"] for r in rows], dtype=float)

        # Compute EMA of HL at two points: now and roc_period bars ago
        ema_now = wilder_ema(hl, params.ema_period)
        ema_prev = wilder_ema(hl[: -params.roc_period], params.ema_period)

        if ema_prev == 0.0:
            return None
        return 100.0 * (ema_now - ema_prev) / ema_prev

    def __repr__(self) -> str:
        return "ChaikinVolatility()"
