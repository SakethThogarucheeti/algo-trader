"""Pivot Points — classic floor-trader pivots from the previous session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

class PivotPoints(Indicator):
    """
    Classic Pivot Points (floor-trader method) from yesterday's session.

    PP  = (H + L + C) / 3
    R1  = 2*PP - L,   S1  = 2*PP - H
    R2  = PP + (H-L), S2  = PP - (H-L)
    R3  = H + 2*(PP-L), S3 = L - 2*(H-PP)

    compute() returns the pivot (PP). Use compute_full() for all levels.
    Fetches yesterday's daily candle (interval="1day"). Returns None when
    no prior-day data is available.
    """

    class Parameters(IndicatorParameters):
        pass

    alias = "pivot"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[0] if result is not None else None

    async def compute_full(
        self, params: Parameters
    ) -> tuple[float, float, float, float, float, float, float] | None:
        # Fetch the two most recent daily bars; use the second-to-last as "yesterday"
        rows = await self._store.fetch(self._symbol, "1day", 2)
        if len(rows) < 2:
            return None

        prev = rows[-2]
        h, lo, c = prev["high"], prev["low"], prev["close"]
        pp = (h + lo + c) / 3.0
        r1 = 2.0 * pp - lo
        s1 = 2.0 * pp - h
        r2 = pp + (h - lo)
        s2 = pp - (h - lo)
        r3 = h + 2.0 * (pp - lo)
        s3 = lo - 2.0 * (h - pp)
        return pp, r1, s1, r2, s2, r3, s3

    def __repr__(self) -> str:
        return "PivotPoints()"
