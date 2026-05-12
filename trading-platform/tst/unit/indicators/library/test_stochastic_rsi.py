"""Tests for indicators/library/stochastic_rsi.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.stochastic_rsi import StochasticRSI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(StochasticRSI, candles([100.0] * 5))
    assert await ind.compute(StochasticRSI.Parameters(rsi_period=14, stoch_period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(100)]
    ind = make_ind(StochasticRSI, candles(closes))
    result = await ind.compute(StochasticRSI.Parameters(rsi_period=14, stoch_period=14))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 7) * 0.5) for i in range(150)]
    ind = make_ind(StochasticRSI, candles(closes))
    result = await ind.compute(StochasticRSI.Parameters())
    assert result is not None
    assert isinstance(result, float)
