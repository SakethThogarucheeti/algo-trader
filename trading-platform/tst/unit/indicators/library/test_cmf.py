"""Tests for indicators/library/cmf.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.cmf import CMF
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(CMF, candles([100.0] * 5))
    assert await ind.compute(CMF.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 5)) for i in range(20)]
    ind = make_ind(CMF, candles(closes))
    result = await ind.compute(CMF.Parameters(period=20))
    assert result is not None
    assert -1.0 <= result <= 1.0
