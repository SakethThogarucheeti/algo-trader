"""Momentum — absolute price change over N bars."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class Momentum(Indicator):
    """
    Momentum: close - close[period] (absolute price change).

    Returns None when fewer than *period* + 1 bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=10, ge=1)

    alias = "momentum"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None
        return rows[-1]["close"] - rows[0]["close"]

    def __repr__(self) -> str:
        return "Momentum()"
