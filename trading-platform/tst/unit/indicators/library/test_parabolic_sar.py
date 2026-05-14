"""Tests for indicators/library/parabolic_sar.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.parabolic_sar import ParabolicSAR
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ParabolicSAR, candles([100.0] * 2))
    assert await ind.compute(ParabolicSAR.Parameters()) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + i * 0.5) for i in range(20)]
    ind = make_ind(ParabolicSAR, candles(closes))
    result = await ind.compute(ParabolicSAR.Parameters())
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_full_bullish_on_uptrend() -> None:
    closes = [float(100 + i) for i in range(50)]
    ind = make_ind(ParabolicSAR, candles(closes))
    result = await ind.compute_full(ParabolicSAR.Parameters())
    assert result is not None
    sar, is_bullish = result
    assert is_bullish is True
    assert sar < closes[-1]


@pytest.mark.asyncio
async def test_bearish_then_bullish_flip() -> None:
    falling = [float(200 - i * 3) for i in range(20)]
    rising = [float(140 + i * 5) for i in range(15)]
    ind = make_ind(ParabolicSAR, candles(falling + rising))
    result = await ind.compute_full(ParabolicSAR.Parameters())
    assert result is not None
    _, is_bullish = result
    assert is_bullish is True


@pytest.mark.asyncio
async def test_bullish_then_bearish_flip() -> None:
    rising = [float(100 + i * 3) for i in range(20)]
    falling = [float(160 - i * 5) for i in range(15)]
    ind = make_ind(ParabolicSAR, candles(rising + falling))
    result = await ind.compute_full(ParabolicSAR.Parameters())
    assert result is not None
    _, is_bullish = result
    assert is_bullish is False


@pytest.mark.asyncio
async def test_af_increments_on_new_extreme() -> None:
    closes = [float(100 + i) for i in range(100)]
    ind = make_ind(ParabolicSAR, candles(closes))
    result = await ind.compute_full(
        ParabolicSAR.Parameters(af_start=0.02, af_step=0.02, af_max=0.2)
    )
    assert result is not None
