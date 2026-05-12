"""Tests for indicators/library/supertrend.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.supertrend import Supertrend
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(Supertrend, candles([100.0] * 5))
    assert await ind.compute(Supertrend.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_direction_is_plus_or_minus_one() -> None:
    closes = [float(100 + i) for i in range(40)]
    ind = make_ind(Supertrend, candles(closes))
    result = await ind.compute(Supertrend.Parameters(period=10, multiplier=3.0))
    assert result is not None
    assert result in (1.0, -1.0)
