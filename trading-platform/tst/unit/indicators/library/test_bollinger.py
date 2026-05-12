"""Tests for indicators/library/bollinger.py"""

from __future__ import annotations

import math

import pytest

from trading.indicators.library.bollinger import BollingerBands
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(BollingerBands, candles([100.0] * 5))
    assert await ind.compute(BollingerBands.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_constant_price_percent_b_half() -> None:
    ind = make_ind(BollingerBands, candles([100.0] * 5))
    result = await ind.compute(BollingerBands.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 0.5, rel_tol=1e-9)


@pytest.mark.asyncio
async def test_full_upper_above_lower() -> None:
    closes = [float(100 + (i % 5)) for i in range(20)]
    ind = make_ind(BollingerBands, candles(closes))
    result = await ind.compute_full(BollingerBands.Parameters(period=20))
    assert result is not None
    upper, middle, lower, bw, pct_b = result
    assert upper > middle > lower
    assert bw >= 0.0
