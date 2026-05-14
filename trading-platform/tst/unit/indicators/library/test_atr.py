"""Tests for indicators/library/atr.py"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.atr import ATR
from trading.indicators.store import CandleStore
from tst.unit.indicators.conftest import candles, make_ind


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ATR, candles([100.0] * 5))
    assert await ind.compute(ATR.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_nonnegative() -> None:
    closes = [100.0 + i * 0.5 for i in range(50)]
    ind = make_ind(ATR, candles(closes))
    result = await ind.compute(ATR.Parameters(period=14))
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_higher_volatility_gives_higher_atr() -> None:
    low_vol = [
        {
            "symbol": "T",
            "interval": "15min",
            "ts": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 1000,
        }
        for i in range(50)
    ]
    high_vol = [
        {
            "symbol": "T",
            "interval": "15min",
            "ts": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
            "volume": 1000,
        }
        for i in range(50)
    ]

    atr_low = ATR(_store(low_vol), "T", "15min")
    atr_high = ATR(_store(high_vol), "T", "15min")

    r_low = await atr_low.compute(ATR.Parameters(period=14))
    r_high = await atr_high.compute(ATR.Parameters(period=14))
    assert r_low is not None and r_high is not None
    assert r_high > r_low
