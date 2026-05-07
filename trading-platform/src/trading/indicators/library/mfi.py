"""Money Flow Index — volume-weighted RSI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class MFI(Indicator):
    """
    Money Flow Index.

    Typical Price (TP) = (H + L + C) / 3
    Raw Money Flow = TP * Volume
    MFI = 100 - 100 / (1 + Positive MF / Negative MF)

    Overbought > 80, oversold < 20.
    Returns None when fewer than *period* + 1 bars are available or when
    negative money flow is zero (all bars up).
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=2)

    alias = "mfi"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None

        tp = np.array(
            [(r["high"] + r["low"] + r["close"]) / 3.0 for r in rows], dtype=float
        )
        vol = np.array([r["volume"] for r in rows], dtype=float)
        raw_mf = tp * vol

        pos_mf = sum(raw_mf[i] for i in range(1, len(rows)) if tp[i] > tp[i - 1])
        neg_mf = sum(raw_mf[i] for i in range(1, len(rows)) if tp[i] < tp[i - 1])

        if neg_mf == 0.0:
            return None  # all up — undefined, same convention as RSI
        return 100.0 - 100.0 / (1.0 + pos_mf / neg_mf)

    def __repr__(self) -> str:
        return "MFI()"
