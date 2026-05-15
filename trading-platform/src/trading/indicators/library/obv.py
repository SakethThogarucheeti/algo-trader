"""On-Balance Volume."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore


class OBV(Indicator):
    """
    On-Balance Volume.

    OBV accumulates volume: add volume when close rises, subtract when it falls.

    The absolute value is arbitrary (depends on start bar); what matters is the
    direction and divergence relative to price.

    Returns None when fewer than 2 bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)

    alias = "obv"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period)
        if len(rows) < 2:
            return None

        obv = 0.0
        for i in range(1, len(rows)):
            if rows[i]["close"] > rows[i - 1]["close"]:
                obv += rows[i]["volume"]
            elif rows[i]["close"] < rows[i - 1]["close"]:
                obv -= rows[i]["volume"]
        return obv

    def __repr__(self) -> str:
        return "OBV()"
