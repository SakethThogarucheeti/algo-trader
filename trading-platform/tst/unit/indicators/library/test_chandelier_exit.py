"""Tests for indicators/library/chandelier_exit.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.chandelier_exit import ChandelierExit
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ChandelierExit, candles([100.0] * 5))
    assert await ind.compute(ChandelierExit.Parameters(period=22)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 5)) for i in range(80)]
    ind = make_ind(ChandelierExit, candles(closes))
    result = await ind.compute(ChandelierExit.Parameters(period=22))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_uptrend_positive_distance() -> None:
    closes = [float(100 + i) for i in range(80)]
    ind = make_ind(ChandelierExit, candles(closes))
    result = await ind.compute(ChandelierExit.Parameters(period=22, multiplier=3.0))
    assert result is not None
    assert result > 0
