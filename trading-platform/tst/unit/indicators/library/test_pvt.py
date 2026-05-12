"""Tests for indicators/library/pvt.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.pvt import PVT
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(PVT, candles([100.0] * 5))
    assert await ind.compute(PVT.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + i * 0.5) for i in range(30)]
    ind = make_ind(PVT, candles(closes))
    result = await ind.compute(PVT.Parameters(period=20))
    assert result is not None
    assert isinstance(result, float)
