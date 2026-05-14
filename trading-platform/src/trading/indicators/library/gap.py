"""Gap Size — session open gap relative to previous close."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

# Gap between bars > this threshold = different session (in minutes of bar time)
_SESSION_GAP_MINUTES = 30


class GapSize(Indicator):
    """
    GapSize: percentage gap between the current session's open and the
    previous session's close.

        gap = (session_open - prev_close) / prev_close * 100

    Sessions are detected by finding a timestamp gap > 30 minutes between
    consecutive bars (works for any intraday interval up to 30min).

    Returns the gap % for every bar in the current session (constant within
    the session — the open does not change). Returns None if only one
    session is present in the buffer (no previous close available) or if
    prev_close is zero.
    """

    class Parameters(IndicatorParameters):
        lookback: int = Field(default=60, ge=2)

    alias = "gap"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        rows = await self._store.fetch(self._symbol, self._interval, params.lookback)
        if len(rows) < 2:
            return None

        timestamps = [r["ts"] for r in rows]
        gap_threshold = timedelta(minutes=_SESSION_GAP_MINUTES)

        # Find most recent session boundary (gap in timestamps)
        session_start_idx = None
        for i in range(len(timestamps) - 1, 0, -1):
            if timestamps[i] - timestamps[i - 1] > gap_threshold:
                session_start_idx = i
                break

        if session_start_idx is None:
            # All bars in same session — no previous session close available
            return None

        session_open = float(rows[session_start_idx]["open"])
        prev_close = float(rows[session_start_idx - 1]["close"])

        if prev_close == 0.0:
            return None

        return (session_open - prev_close) / prev_close * 100.0

    def __repr__(self) -> str:
        return "GapSize()"
