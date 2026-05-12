"""Tests for indicators/library/squeeze_momentum.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.squeeze_momentum import SqueezeMomentum
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(SqueezeMomentum, candles([100.0] * 5))
    assert await ind.compute(SqueezeMomentum.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 5)) for i in range(70)]
    ind = make_ind(SqueezeMomentum, candles(closes))
    result = await ind.compute(SqueezeMomentum.Parameters(period=20))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_uptrend_positive_momentum() -> None:
    closes = [float(100 + i) for i in range(70)]
    ind = make_ind(SqueezeMomentum, candles(closes))
    result = await ind.compute(SqueezeMomentum.Parameters(period=20))
    assert result is not None
    assert result > 0
