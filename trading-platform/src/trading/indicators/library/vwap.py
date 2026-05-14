"""Session VWAP — cumulative volume-weighted average price from today's 09:15 IST open."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

import numpy as np

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_SESSION_OPEN = time(9, 15)


class VWAP(Indicator):
    """
    Cumulative session VWAP for the current trading day (NSE / 09:15 IST reset).

    Fetches all candles from today's session open onward via ``fetch_since()``.
    Pass a ``SimulatedClock`` during backtesting so the session boundary is
    derived from the replayed bar's timestamp rather than wall-clock time.
    Returns None when no bars have been ingested for the current session or
    total volume is zero.
    """

    class Parameters(IndicatorParameters):
        pass

    alias = "vwap"

    def __init__(
        self, store: CandleStore, symbol: str, interval: str, clock: Clock = SYSTEM_CLOCK
    ) -> None:
        super().__init__(store, symbol, interval)
        self._clock = clock

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        since = self._clock.session_open_utc(_SESSION_OPEN)
        rows = await self._store.fetch_since(self._symbol, self._interval, since)
        if not rows:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        volumes = np.array([r["volume"] for r in rows], dtype=float)

        total_vol = volumes.sum()
        if total_vol == 0.0:
            return None

        return float((closes * volumes).sum() / total_vol)

    def __repr__(self) -> str:
        return "VWAP()"
