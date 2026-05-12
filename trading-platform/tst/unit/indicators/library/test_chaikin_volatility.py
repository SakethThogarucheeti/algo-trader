"""Tests for indicators/library/chaikin_volatility.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.chaikin_volatility import ChaikinVolatility
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ChaikinVolatility, candles([100.0] * 5))
    assert await ind.compute(ChaikinVolatility.Parameters(ema_period=10, roc_period=10)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 5)) for i in range(60)]
    ind = make_ind(ChaikinVolatility, candles(closes))
    result = await ind.compute(ChaikinVolatility.Parameters(ema_period=10, roc_period=10))
    assert result is not None
    assert isinstance(result, float)
