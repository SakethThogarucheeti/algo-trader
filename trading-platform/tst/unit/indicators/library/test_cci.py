"""Tests for indicators/library/cci.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.cci import CCI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(CCI, candles([100.0] * 5))
    assert await ind.compute(CCI.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_flat_returns_none() -> None:
    ind = make_ind(CCI, candles([100.0] * 5))
    assert await ind.compute(CCI.Parameters(period=5)) is None


@pytest.mark.asyncio
async def test_overbought_on_spike() -> None:
    closes = [100.0] * 19 + [120.0]
    ind = make_ind(CCI, candles(closes))
    result = await ind.compute(CCI.Parameters(period=20))
    assert result is not None
    assert result > 100.0
