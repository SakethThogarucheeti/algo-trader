"""Parabolic SAR."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class ParabolicSAR(Indicator):
    """
    Parabolic SAR (Stop and Reverse).

    compute() returns the current SAR value (price level).
    Use compute_full() for (sar, is_bullish).

    Returns None when fewer than 3 bars are available.
    """

    class Parameters(IndicatorParameters):
        af_start: float = Field(default=0.02, gt=0)
        af_step: float = Field(default=0.02, gt=0)
        af_max: float = Field(default=0.2, gt=0)

    alias = "psar"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[0] if result is not None else None

    async def compute_full(self, params: Parameters) -> tuple[float, bool] | None:
        rows = await self._store.fetch(self._symbol, self._interval, 100)
        if len(rows) < 3:
            return None

        highs = [r["high"] for r in rows]
        lows = [r["low"] for r in rows]

        # Initialise: assume uptrend from first bar
        bullish = True
        sar = lows[0]
        ep = highs[0]  # extreme point
        af = params.af_start

        for i in range(1, len(rows)):
            prev_sar = sar
            sar = prev_sar + af * (ep - prev_sar)

            if bullish:
                sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
                if lows[i] < sar:
                    bullish = False
                    sar = ep
                    ep = lows[i]
                    af = params.af_start
                else:
                    if highs[i] > ep:
                        ep = highs[i]
                        af = min(af + params.af_step, params.af_max)
            else:
                sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
                if highs[i] > sar:
                    bullish = True
                    sar = ep
                    ep = highs[i]
                    af = params.af_start
                else:
                    if lows[i] < ep:
                        ep = lows[i]
                        af = min(af + params.af_step, params.af_max)

        return float(sar), bullish

    def __repr__(self) -> str:
        return "ParabolicSAR()"
