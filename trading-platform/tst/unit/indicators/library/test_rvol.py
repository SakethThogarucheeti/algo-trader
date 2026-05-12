"""Tests for indicators/library/rvol.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.rvol import RVOL
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(RVOL, candles([100.0] * 5))
    assert await ind.compute(RVOL.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [100.0] * 25
    ind = make_ind(RVOL, candles(closes))
    result = await ind.compute(RVOL.Parameters(period=20))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_average_volume_gives_one() -> None:
    closes = [100.0] * 25
    ind = make_ind(RVOL, candles(closes))
    result = await ind.compute(RVOL.Parameters(period=20))
    assert result is not None
    assert result == pytest.approx(1.0, rel=1e-4)
