"""Tests for indicators/library/sma.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.sma import SMA
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_exact_mean() -> None:
    ind = make_ind(SMA, candles([10.0, 20.0, 30.0, 40.0, 50.0]))
    result = await ind.compute(SMA.Parameters(period=5))
    assert result == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(SMA, candles([100.0] * 5))
    assert await ind.compute(SMA.Parameters(period=10)) is None
