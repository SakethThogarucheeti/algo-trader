"""Tests for indicators/library/keltner.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.keltner import KeltnerChannels
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(KeltnerChannels, candles([100.0] * 5))
    assert await ind.compute(KeltnerChannels.Parameters()) is None


@pytest.mark.asyncio
async def test_full_upper_above_lower() -> None:
    closes = [float(100 + (i % 5)) for i in range(60)]
    ind = make_ind(KeltnerChannels, candles(closes))
    result = await ind.compute_full(KeltnerChannels.Parameters(ema_period=20, atr_period=10))
    assert result is not None
    upper, middle, lower = result
    assert upper > middle > lower
