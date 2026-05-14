"""Session High-Low Pct — position within today's intraday range."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

import numpy as np

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_SESSION_OPEN = time(9, 15)


class SessionHighLowPct(Indicator):
    """
    Position of the current close within today's session range so far.

        (close - session_low) / (session_high - session_low)

    Returns [0, 1]: 0 = at session low, 1 = at session high.
    Returns None if fewer than 2 session bars are available or range == 0.
    """

    class Parameters(IndicatorParameters):
        pass

    alias = "session_hl_pct"

    def __init__(
        self, store: CandleStore, symbol: str, interval: str, clock: Clock = SYSTEM_CLOCK
    ) -> None:
        super().__init__(store, symbol, interval)
        self._clock = clock

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        since = self._clock.session_open_utc(_SESSION_OPEN)
        rows = await self._store.fetch_since(self._symbol, self._interval, since)
        if len(rows) < 2:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)

        session_high = float(np.max(highs))
        session_low = float(np.min(lows))
        rng = session_high - session_low

        if rng == 0.0:
            return None

        current_close = float(rows[-1]["close"])
        return (current_close - session_low) / rng

    def __repr__(self) -> str:
        return "SessionHighLowPct()"
