"""Rate of Change (price momentum)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class ROC(Indicator):
    """
    Rate of Change: percentage change in close over *period* bars.

    ROC = 100 * (close - close[period]) / close[period]

    Returns None when fewer than *period* + 1 bars are available or
    when the reference close is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=10, ge=1)

    alias = "roc"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None

        ref = rows[0]["close"]
        if ref == 0.0:
            return None
        return 100.0 * (rows[-1]["close"] - ref) / ref

    def __repr__(self) -> str:
        return "ROC()"
