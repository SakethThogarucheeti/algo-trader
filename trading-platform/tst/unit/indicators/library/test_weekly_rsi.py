"""Tests for indicators/library/weekly_rsi.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.weekly_rsi import WeeklyRSI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(WeeklyRSI, candles([100.0] * 5))
    assert await ind.compute(WeeklyRSI.Parameters(rsi_period=14, week_bars=5)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(300)]
    ind = make_ind(WeeklyRSI, candles(closes))
    result = await ind.compute(WeeklyRSI.Parameters(rsi_period=14, week_bars=5))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_uptrend_high_rsi() -> None:
    closes = [float(100 + i) for i in range(300)]
    ind = make_ind(WeeklyRSI, candles(closes))
    result = await ind.compute(WeeklyRSI.Parameters(rsi_period=14, week_bars=5))
    assert result is not None
    assert result > 50.0
