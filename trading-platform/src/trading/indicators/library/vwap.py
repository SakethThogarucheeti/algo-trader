"""Session VWAP — cumulative volume-weighted average price from today's 09:15 IST open."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import UTC, datetime, time, timedelta

import numpy as np
from pydantic import Field

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

# NSE session open in IST = 09:15 → UTC = 03:45
_SESSION_OPEN_IST = time(9, 15)
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _today_session_open_utc(now: datetime) -> datetime:
    """Return today's 09:15 IST as a UTC datetime."""
    ist_now = now + _IST_OFFSET
    session_open_ist = datetime(
        ist_now.year, ist_now.month, ist_now.day,
        _SESSION_OPEN_IST.hour, _SESSION_OPEN_IST.minute,
        tzinfo=UTC,
    ) - _IST_OFFSET
    return session_open_ist


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

    def __init__(self, store: CandleStore, symbol: str, interval: str, clock: Clock = SYSTEM_CLOCK) -> None:
        super().__init__(store, symbol, interval)
        self._clock = clock

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        since = _today_session_open_utc(self._clock.now())
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
