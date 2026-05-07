"""Historical Volatility — annualised close-to-close log-return std dev."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_TRADING_DAYS_PER_YEAR = 252


class HistoricalVolatility(Indicator):
    """
    Historical Volatility (close-to-close, annualised).

    HV = std(log(close[i] / close[i-1])) * sqrt(trading_days)

    Returns the annualised volatility as a decimal (e.g. 0.25 = 25%).
    Returns None when fewer than *period* + 1 bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=2)
        trading_days: int = Field(default=252, ge=1)

    alias = "hv"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        if np.any(closes <= 0):
            return None

        log_returns = np.log(closes[1:] / closes[:-1])
        return float(np.std(log_returns, ddof=1) * np.sqrt(params.trading_days))

    def __repr__(self) -> str:
        return "HistoricalVolatility()"
