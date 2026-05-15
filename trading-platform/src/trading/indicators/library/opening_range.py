"""Opening Range Position — close position within the first-hour range."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_SESSION_GAP_MINUTES = 30


class OpeningRangePosition(Indicator):
    """
    Opening Range Position.

    Computes the high and low of the first *range_bars* bars of the
    current session (e.g. 4 × 15min = first hour), then returns:

        (close - OR_low) / (OR_high - OR_low)

    Returns [0, 1]: 0 = at bottom of opening range, 1 = at top.
    Returns None if the current session has fewer than *range_bars* bars,
    or if OR_high == OR_low (flat opening).
    """

    class Parameters(IndicatorParameters):
        range_bars: int = Field(default=4, ge=1)

    alias = "opening_range"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        # Fetch enough to cover the opening range + some prior session
        limit = params.range_bars + 60
        rows = await self._store.fetch(self._symbol, self._interval, limit)
        if len(rows) < params.range_bars + 1:
            return None

        timestamps = [r["ts"] for r in rows]
        gap_threshold = timedelta(minutes=_SESSION_GAP_MINUTES)

        # Find start of current session
        session_start_idx = 0
        for i in range(len(timestamps) - 1, 0, -1):
            if timestamps[i] - timestamps[i - 1] > gap_threshold:
                session_start_idx = i
                break

        session_rows = rows[session_start_idx:]
        if len(session_rows) < params.range_bars:
            return None

        or_rows = session_rows[: params.range_bars]
        or_high = float(max(r["high"] for r in or_rows))
        or_low = float(min(r["low"] for r in or_rows))

        rng = or_high - or_low
        if rng == 0.0:
            return None

        current_close = float(rows[-1]["close"])
        return (current_close - or_low) / rng

    def __repr__(self) -> str:
        return "OpeningRangePosition()"
