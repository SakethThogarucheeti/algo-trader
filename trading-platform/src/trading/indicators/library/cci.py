"""Commodity Channel Index."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class CCI(Indicator):
    """
    Commodity Channel Index.

    CCI = (Typical Price - SMA(TP, period)) / (0.015 * Mean Absolute Deviation)

    Typical Price = (High + Low + Close) / 3

    Overbought > +100, oversold < -100.
    Returns None when fewer than *period* bars are available or MAD is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=1)

    alias = "cci"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < params.period:
            return None

        tp = np.array([(r["high"] + r["low"] + r["close"]) / 3.0 for r in rows], dtype=float)
        sma_tp = float(np.mean(tp))
        mad = float(np.mean(np.abs(tp - sma_tp)))
        if mad == 0.0:
            return None
        return float((tp[-1] - sma_tp) / (0.015 * mad))

    def __repr__(self) -> str:
        return "CCI()"
