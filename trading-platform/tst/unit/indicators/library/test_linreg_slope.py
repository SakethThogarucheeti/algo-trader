"""Tests for indicators/library/linreg_slope.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.linreg_slope import LinearRegressionSlope
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(LinearRegressionSlope, candles([100.0] * 5))
    assert await ind.compute(LinearRegressionSlope.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i) for i in range(30)]
    ind = make_ind(LinearRegressionSlope, candles(closes))
    result = await ind.compute(LinearRegressionSlope.Parameters(period=20))
    assert result is not None
    assert result > 0


@pytest.mark.asyncio
async def test_downtrend_negative() -> None:
    closes = [float(200 - i) for i in range(30)]
    ind = make_ind(LinearRegressionSlope, candles(closes))
    result = await ind.compute(LinearRegressionSlope.Parameters(period=20))
    assert result is not None
    assert result < 0


@pytest.mark.asyncio
async def test_flat_near_zero() -> None:
    closes = [100.0] * 30
    ind = make_ind(LinearRegressionSlope, candles(closes))
    result = await ind.compute(LinearRegressionSlope.Parameters(period=20))
    assert result is not None
    assert abs(result) < 1e-6
