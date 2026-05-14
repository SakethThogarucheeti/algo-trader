"""Tests for indicators/library/ultimate_oscillator.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.ultimate_oscillator import UltimateOscillator
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(UltimateOscillator, candles([100.0] * 10))
    assert (
        await ind.compute(UltimateOscillator.Parameters(period1=7, period2=14, period3=28)) is None
    )


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 5)) for i in range(40)]
    ind = make_ind(UltimateOscillator, candles(closes))
    result = await ind.compute(UltimateOscillator.Parameters(period1=7, period2=14, period3=28))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_invalid_period_order_returns_none() -> None:
    closes = [float(100 + i) for i in range(40)]
    ind = make_ind(UltimateOscillator, candles(closes))
    result = await ind.compute(UltimateOscillator.Parameters(period1=14, period2=7, period3=28))
    assert result is None
