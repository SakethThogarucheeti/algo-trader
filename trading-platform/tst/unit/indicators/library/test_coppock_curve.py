"""Tests for indicators/library/coppock_curve.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.coppock_curve import CoppockCurve
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(CoppockCurve, candles([100.0] * 5))
    assert await ind.compute(CoppockCurve.Parameters(wma_period=10, roc1_period=14, roc2_period=11)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + i * 0.5) for i in range(60)]
    ind = make_ind(CoppockCurve, candles(closes))
    result = await ind.compute(CoppockCurve.Parameters(wma_period=10, roc1_period=14, roc2_period=11))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i) for i in range(60)]
    ind = make_ind(CoppockCurve, candles(closes))
    result = await ind.compute(CoppockCurve.Parameters(wma_period=10, roc1_period=14, roc2_period=11))
    assert result is not None
    assert result > 0
