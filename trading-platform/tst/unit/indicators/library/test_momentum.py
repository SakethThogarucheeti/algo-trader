"""Tests for indicators/library/momentum.py"""

from __future__ import annotations

import math

import pytest

from trading.indicators.library.momentum import Momentum
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(Momentum, candles([100.0] * 5))
    assert await ind.compute(Momentum.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_flat_is_zero() -> None:
    ind = make_ind(Momentum, candles([100.0] * 6))
    result = await ind.compute(Momentum.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_positive_on_rise() -> None:
    ind = make_ind(Momentum, candles([100.0, 101.0, 102.0, 105.0]))
    result = await ind.compute(Momentum.Parameters(period=3))
    assert result is not None
    assert result > 0.0
