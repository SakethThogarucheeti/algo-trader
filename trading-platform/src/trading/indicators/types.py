from __future__ import annotations

from datetime import datetime
from typing import TypedDict


class CandleRow(TypedDict):
    """One OHLCV row as returned by CandleStore.fetch() / PolarsStore.fetch()."""

    symbol: str
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
