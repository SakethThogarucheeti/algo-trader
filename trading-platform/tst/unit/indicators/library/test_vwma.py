"""Tests for indicators/library/vwma.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.vwma import VWMA
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(VWMA, candles([100.0] * 5))
    assert await ind.compute(VWMA.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_equal_volumes_equals_sma() -> None:
    closes = [float(i) for i in range(1, 6)]
    ind = make_ind(VWMA, candles(closes))
    result = await ind.compute(VWMA.Parameters(period=5))
    expected = sum(closes) / len(closes)
    assert result is not None
    assert result == pytest.approx(expected, rel=1e-9)
