"""Tests for indicators/library/distance_from_ma.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.distance_from_ma import DistanceFromMA
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(DistanceFromMA, candles([100.0] * 5))
    assert await ind.compute(DistanceFromMA.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_at_ma_gives_zero() -> None:
    closes = [100.0] * 25
    ind = make_ind(DistanceFromMA, candles(closes))
    result = await ind.compute(DistanceFromMA.Parameters(period=20))
    assert result is not None
    assert result == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_uptrend_positive_distance() -> None:
    closes = [float(90 + i) for i in range(30)]
    ind = make_ind(DistanceFromMA, candles(closes))
    result = await ind.compute(DistanceFromMA.Parameters(period=20))
    assert result is not None
    assert result > 0
