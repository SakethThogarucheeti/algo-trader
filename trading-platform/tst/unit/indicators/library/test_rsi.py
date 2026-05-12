"""Tests for indicators/library/rsi.py"""

from __future__ import annotations

import random

import pytest

from trading.indicators.library.rsi import RSI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(RSI, candles([100.0] * 10))
    assert await ind.compute(RSI.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_flat_market_returns_none() -> None:
    ind = make_ind(RSI, candles([100.0] * 50))
    assert await ind.compute(RSI.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_monotonic_uptrend_returns_none() -> None:
    closes = [float(100 + i) for i in range(50)]
    ind = make_ind(RSI, candles(closes))
    assert await ind.compute(RSI.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_uptrend_with_pullback_near_100() -> None:
    closes = []
    price = 100.0
    for i in range(50):
        if i > 0 and i % 5 == 0:
            price -= 0.5
        else:
            price += 1.5
        closes.append(price)
    ind = make_ind(RSI, candles(closes))
    result = await ind.compute(RSI.Parameters(period=14))
    assert result is not None
    assert result > 70.0


@pytest.mark.asyncio
async def test_downtrend_near_0() -> None:
    closes = [float(200 - i) for i in range(50)]
    ind = make_ind(RSI, candles(closes))
    result = await ind.compute(RSI.Parameters(period=14))
    assert result is not None
    assert result < 20.0


@pytest.mark.asyncio
async def test_in_valid_range() -> None:
    random.seed(42)
    closes = [100.0 + random.gauss(0, 2) for _ in range(60)]
    ind = make_ind(RSI, candles(closes))
    result = await ind.compute(RSI.Parameters(period=14))
    if result is not None:
        assert 0.0 <= result <= 100.0
