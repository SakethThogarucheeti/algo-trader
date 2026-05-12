"""Tests for indicators/library/vwap.py"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.vwap import VWAP
from trading.indicators.store import CandleStore


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_single_bar() -> None:
    rows = [{"symbol": "T", "interval": "15min",
             "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
             "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 500}]
    ind = VWAP(_store(rows), "T", "15min")
    result = await ind.compute(VWAP.Parameters())
    assert result == pytest.approx(102.0)


@pytest.mark.asyncio
async def test_weighted_correctly() -> None:
    rows = [
        {"symbol": "T", "interval": "15min",
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
         "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 100},
        {"symbol": "T", "interval": "15min",
         "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
         "open": 200.0, "high": 200.0, "low": 200.0, "close": 200.0, "volume": 300},
    ]
    ind = VWAP(_store(rows), "T", "15min")
    result = await ind.compute(VWAP.Parameters())
    assert result == pytest.approx(175.0)


@pytest.mark.asyncio
async def test_zero_volume_returns_none() -> None:
    rows = [{"symbol": "T", "interval": "15min",
             "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
             "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0}]
    ind = VWAP(_store(rows), "T", "15min")
    assert await ind.compute(VWAP.Parameters()) is None


@pytest.mark.asyncio
async def test_no_bars_returns_none() -> None:
    ind = VWAP(_store([]), "T", "15min")
    assert await ind.compute(VWAP.Parameters()) is None
