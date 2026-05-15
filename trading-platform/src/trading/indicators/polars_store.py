"""PolarsStore — in-memory CandleStore backed by a rolling Polars buffer.

Satisfies the same fetch()/fetch_since() interface as CandleStore so all
indicator objects work unchanged without a Postgres connection.  Used during
backtesting and live trading warmup before the DB is populated.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from trading.indicators.store import AbstractCandleStore
from trading.indicators.types import CandleRow


class PolarsStore(AbstractCandleStore):
    """
    In-memory candle store.  Feed bars in with push(); indicators call
    fetch() / fetch_since() identically to the Postgres-backed CandleStore.

    One PolarsStore instance is shared across all indicators bound to the
    same (symbol, interval).  AlgoRegistry calls push() on each CandleEvent
    before invoking strategy.on_candle(), so indicators always see the
    current bar.
    """

    def __init__(self, maxlen: int = 500) -> None:
        # (symbol, interval) → deque of candle dicts (oldest first)
        self._buffers: dict[tuple[str, str], deque[CandleRow]] = {}
        self._maxlen = maxlen

    def push(self, symbol: str, interval: str, row: CandleRow) -> None:
        """Append a candle row dict to the rolling buffer."""
        key = (symbol, interval)
        if key not in self._buffers:
            self._buffers[key] = deque(maxlen=self._maxlen)
        self._buffers[key].append(row)

    # ------------------------------------------------------------------
    # CandleStore-compatible async interface
    # ------------------------------------------------------------------

    async def fetch(self, symbol: str, interval: str, limit: int) -> list[CandleRow]:
        """Return the last *limit* candles ordered ts ASC (oldest→newest)."""
        buf = self._buffers.get((symbol, interval))
        if not buf:
            return []
        return list(buf)[-limit:]

    async def fetch_since(self, symbol: str, interval: str, since: datetime) -> list[CandleRow]:
        """Return all candles with ts >= *since*, ordered ts ASC."""
        buf = self._buffers.get((symbol, interval))
        if not buf:
            return []
        return [r for r in buf if r["ts"] >= since]
