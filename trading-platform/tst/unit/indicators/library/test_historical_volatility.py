"""Tests for indicators/library/historical_volatility.py"""

from __future__ import annotations

import math
import random

import pytest

from trading.indicators.library.historical_volatility import HistoricalVolatility
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(HistoricalVolatility, candles([100.0] * 5))
    assert await ind.compute(HistoricalVolatility.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_flat_is_zero() -> None:
    ind = make_ind(HistoricalVolatility, candles([100.0] * 6))
    result = await ind.compute(HistoricalVolatility.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_positive_on_volatile_series() -> None:
    random.seed(7)
    closes = [100.0 * (1 + random.gauss(0, 0.02)) for _ in range(22)]
    ind = make_ind(HistoricalVolatility, candles(closes))
    result = await ind.compute(HistoricalVolatility.Parameters(period=20))
    assert result is not None
    assert result > 0.0
