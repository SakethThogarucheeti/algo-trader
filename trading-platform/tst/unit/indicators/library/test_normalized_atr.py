"""Tests for indicators/library/normalized_atr.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.normalized_atr import NormalizedATR
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(NormalizedATR, candles([100.0] * 5))
    assert await ind.compute(NormalizedATR.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_returns_positive_float() -> None:
    closes = [float(100 + (i % 5)) for i in range(50)]
    ind = make_ind(NormalizedATR, candles(closes))
    result = await ind.compute(NormalizedATR.Parameters(period=14))
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_more_volatile_higher_value() -> None:
    calm = [float(100 + (i % 2)) for i in range(50)]
    volatile = [float(100 + (i % 10)) for i in range(50)]
    ind_calm = make_ind(NormalizedATR, candles(calm))
    ind_volatile = make_ind(NormalizedATR, candles(volatile))
    r_calm = await ind_calm.compute(NormalizedATR.Parameters(period=14))
    r_volatile = await ind_volatile.compute(NormalizedATR.Parameters(period=14))
    assert r_calm is not None
    assert r_volatile is not None
    assert r_volatile > r_calm
