"""Tests for indicators/library/fisher_transform.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.fisher_transform import FisherTransform
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(FisherTransform, candles([100.0] * 5))
    assert await ind.compute(FisherTransform.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + i) for i in range(20)]
    ind = make_ind(FisherTransform, candles(closes))
    result = await ind.compute(FisherTransform.Parameters(period=10))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i) for i in range(20)]
    ind = make_ind(FisherTransform, candles(closes))
    result = await ind.compute(FisherTransform.Parameters(period=10))
    assert result is not None
    assert result > 0
