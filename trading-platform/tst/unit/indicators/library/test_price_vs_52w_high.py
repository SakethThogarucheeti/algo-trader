"""Tests for indicators/library/price_vs_52w_high.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.price_vs_52w_high import PriceVs52wHigh
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(PriceVs52wHigh, candles([100.0] * 5))
    assert await ind.compute(PriceVs52wHigh.Parameters(period=252)) is None


@pytest.mark.asyncio
async def test_at_high_gives_zero_or_negative() -> None:
    closes = [float(100 + i) for i in range(10)]
    ind = make_ind(PriceVs52wHigh, candles(closes))
    result = await ind.compute(PriceVs52wHigh.Parameters(period=10))
    assert result is not None
    assert result <= 0


@pytest.mark.asyncio
async def test_below_high_gives_negative() -> None:
    closes = list(range(100, 110)) + [95.0]
    ind = make_ind(PriceVs52wHigh, candles([float(c) for c in closes]))
    result = await ind.compute(PriceVs52wHigh.Parameters(period=len(closes)))
    assert result is not None
    assert result < 0


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 7)) for i in range(20)]
    ind = make_ind(PriceVs52wHigh, candles(closes))
    result = await ind.compute(PriceVs52wHigh.Parameters(period=15))
    assert result is not None
    assert isinstance(result, float)
