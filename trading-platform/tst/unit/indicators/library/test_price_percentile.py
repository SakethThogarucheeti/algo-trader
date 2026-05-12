"""Tests for indicators/library/price_percentile.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.price_percentile import PricePercentile
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(PricePercentile, candles([100.0] * 5))
    assert await ind.compute(PricePercentile.Parameters(period=50)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + i) for i in range(60)]
    ind = make_ind(PricePercentile, candles(closes))
    result = await ind.compute(PricePercentile.Parameters(period=50))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_highest_in_window_gives_100() -> None:
    closes = list(range(51))
    ind = make_ind(PricePercentile, candles([float(c) for c in closes]))
    result = await ind.compute(PricePercentile.Parameters(period=50))
    assert result is not None
    assert result == pytest.approx(100.0, rel=1e-4)
