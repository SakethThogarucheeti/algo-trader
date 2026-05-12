"""Tests for indicators/library/donchian.py"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.donchian import DonchianChannels
from trading.indicators.store import CandleStore
from tst.unit.indicators.conftest import candles, make_ind


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(DonchianChannels, candles([100.0] * 5))
    assert await ind.compute(DonchianChannels.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_full_upper_lower() -> None:
    closes = [float(90 + i) for i in range(20)]
    ind = make_ind(DonchianChannels, candles(closes))
    result = await ind.compute_full(DonchianChannels.Parameters(period=20))
    assert result is not None
    upper, middle, lower = result
    assert upper >= middle >= lower


@pytest.mark.asyncio
async def test_flat_width_zero() -> None:
    rows = [
        {"symbol": "X", "interval": "15min",
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
         "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000}
        for _ in range(5)
    ]
    ind = DonchianChannels(_store(rows), "TEST", "15min")
    result = await ind.compute_full(DonchianChannels.Parameters(period=5))
    assert result is not None
    upper, middle, lower = result
    assert math.isclose(upper, lower, abs_tol=1e-9)
