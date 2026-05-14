"""Tests for indicators/library/ema.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.ema import EMA
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(EMA, candles([100.0] * 5))
    assert await ind.compute(EMA.Parameters(period=9)) is None


@pytest.mark.asyncio
async def test_constant_price() -> None:
    ind = make_ind(EMA, candles([150.0] * 30))
    result = await ind.compute(EMA.Parameters(period=9))
    assert result == pytest.approx(150.0, rel=1e-4)


@pytest.mark.asyncio
async def test_uptrend_lags_price() -> None:
    closes = list(range(100, 140))
    ind = make_ind(EMA, candles(closes))
    result = await ind.compute(EMA.Parameters(period=9))
    assert result is not None
    assert result < closes[-1]
    assert result > closes[0]


def test_period_zero_raises() -> None:
    with pytest.raises(ValueError):
        EMA.Parameters(period=0)
