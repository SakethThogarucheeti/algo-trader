"""Tests for indicators/library/vroc.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.vroc import VROC
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(VROC, candles([100.0] * 5))
    assert await ind.compute(VROC.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [100.0] * 20
    ind = make_ind(VROC, candles(closes))
    result = await ind.compute(VROC.Parameters(period=14))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_constant_volume_gives_zero() -> None:
    closes = [100.0] * 20
    ind = make_ind(VROC, candles(closes))
    result = await ind.compute(VROC.Parameters(period=14))
    assert result is not None
    assert result == pytest.approx(0.0, abs=1e-9)
