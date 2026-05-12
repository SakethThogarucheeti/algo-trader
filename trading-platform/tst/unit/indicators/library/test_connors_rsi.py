"""Tests for indicators/library/connors_rsi.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.connors_rsi import ConnorsRSI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ConnorsRSI, candles([100.0] * 5))
    assert await ind.compute(ConnorsRSI.Parameters(rsi_period=3, streak_period=2, rank_period=100)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(200)]
    ind = make_ind(ConnorsRSI, candles(closes))
    result = await ind.compute(ConnorsRSI.Parameters(rsi_period=3, streak_period=2, rank_period=100))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 7) * 0.5) for i in range(400)]
    ind = make_ind(ConnorsRSI, candles(closes))
    result = await ind.compute(ConnorsRSI.Parameters())
    assert result is not None
    assert isinstance(result, float)
