"""Tests for indicators/library/volatility_ratio.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.volatility_ratio import VolatilityRatio
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(VolatilityRatio, candles([100.0] * 10))
    assert await ind.compute(VolatilityRatio.Parameters(atr_period=14, smooth_period=50)) is None


@pytest.mark.asyncio
async def test_returns_positive_float() -> None:
    closes = [float(100 + (i % 5)) for i in range(200)]
    ind = make_ind(VolatilityRatio, candles(closes))
    result = await ind.compute(VolatilityRatio.Parameters(atr_period=14, smooth_period=50))
    assert result is not None
    assert result > 0.0
