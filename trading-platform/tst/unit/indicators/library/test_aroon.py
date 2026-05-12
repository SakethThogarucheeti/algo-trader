"""Tests for indicators/library/aroon.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.aroon import Aroon
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(Aroon, candles([100.0] * 5))
    assert await ind.compute(Aroon.Parameters(period=25)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 5)) for i in range(60)]
    ind = make_ind(Aroon, candles(closes))
    result = await ind.compute(Aroon.Parameters(period=25))
    assert result is not None
    assert -100.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i) for i in range(60)]
    ind = make_ind(Aroon, candles(closes))
    result = await ind.compute(Aroon.Parameters(period=25))
    assert result is not None
    assert result > 0
