"""Tests for indicators/library/inside_bar.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.inside_bar import InsideBar
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(InsideBar, candles([100.0] * 3))
    assert await ind.compute(InsideBar.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 3)) for i in range(25)]
    ind = make_ind(InsideBar, candles(closes))
    result = await ind.compute(InsideBar.Parameters(period=10))
    assert result is not None
    assert 0.0 <= result <= 1.0


@pytest.mark.asyncio
async def test_no_inside_bars_gives_zero() -> None:
    closes = [float(100 + i * 5) for i in range(25)]
    ind = make_ind(InsideBar, candles(closes))
    result = await ind.compute(InsideBar.Parameters(period=10))
    assert result is not None
    assert result == pytest.approx(0.0, abs=1e-9)
