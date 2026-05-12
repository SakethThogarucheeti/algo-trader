"""Tests for indicators/library/adx.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.adx import ADX
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ADX, candles([100.0] * 10))
    assert await ind.compute(ADX.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(60)]
    ind = make_ind(ADX, candles(closes))
    result = await ind.compute(ADX.Parameters(period=14))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_full_returns_three() -> None:
    closes = [float(100 + i) for i in range(60)]
    ind = make_ind(ADX, candles(closes))
    result = await ind.compute_full(ADX.Parameters(period=14))
    assert result is not None
    adx, plus_di, minus_di = result
    assert adx >= 0.0
    assert plus_di >= 0.0
    assert minus_di >= 0.0
