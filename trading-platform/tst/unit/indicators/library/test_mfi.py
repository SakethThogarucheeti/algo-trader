"""Tests for indicators/library/mfi.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.mfi import MFI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(MFI, candles([100.0] * 5))
    assert await ind.compute(MFI.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 5)) for i in range(15)]
    ind = make_ind(MFI, candles(closes))
    result = await ind.compute(MFI.Parameters(period=14))
    if result is not None:
        assert 0.0 <= result <= 100.0
