"""Tests for indicators/library/upper_shadow_ratio.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.upper_shadow_ratio import UpperShadowRatio
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(UpperShadowRatio, candles([100.0] * 2))
    assert await ind.compute(UpperShadowRatio.Parameters(period=5)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + i) for i in range(15)]
    ind = make_ind(UpperShadowRatio, candles(closes))
    result = await ind.compute(UpperShadowRatio.Parameters(period=5))
    assert result is not None
    assert 0.0 <= result <= 1.0


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 3)) for i in range(15)]
    ind = make_ind(UpperShadowRatio, candles(closes))
    result = await ind.compute(UpperShadowRatio.Parameters(period=5))
    assert result is not None
    assert isinstance(result, float)
