"""Tests for indicators/library/mean_reversion_score.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.mean_reversion_score import MeanReversionScore
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(MeanReversionScore, candles([100.0] * 5))
    assert await ind.compute(MeanReversionScore.Parameters(period=20, rsi_period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(80)]
    ind = make_ind(MeanReversionScore, candles(closes))
    result = await ind.compute(MeanReversionScore.Parameters(period=20, rsi_period=14))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_overbought_has_high_score() -> None:
    closes = [float(100 + i * 2) for i in range(80)]
    ind = make_ind(MeanReversionScore, candles(closes))
    result = await ind.compute(MeanReversionScore.Parameters(period=20, rsi_period=14))
    assert result is not None
    assert result > 50.0
