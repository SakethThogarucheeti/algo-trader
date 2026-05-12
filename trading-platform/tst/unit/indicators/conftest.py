"""Shared helpers for indicator unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from trading.indicators.store import CandleStore


def make_store(rows: list[dict]) -> CandleStore:
    store = MagicMock(spec=CandleStore)
    store.fetch = AsyncMock(return_value=rows)
    store.fetch_since = AsyncMock(return_value=rows)
    return store


def candles(closes: list[float], *, base_ts: datetime | None = None) -> list[dict]:
    if base_ts is None:
        base_ts = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    rows = []
    for i, c in enumerate(closes):
        ts = base_ts + timedelta(minutes=15 * i)
        rows.append({
            "symbol": "TEST",
            "interval": "15min",
            "ts": ts,
            "open": c,
            "high": c + 1.0,
            "low": c - 1.0,
            "close": c,
            "volume": 1000,
        })
    return rows


def make_ind(cls, rows: list[dict], symbol: str = "TEST", interval: str = "15min"):
    """Construct an indicator bound to a stub store."""
    return cls(make_store(rows), symbol, interval)
