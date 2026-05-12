"""Tests for indicators/library/tsi.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.tsi import TSI
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(TSI, candles([100.0] * 10))
    assert await ind.compute(TSI.Parameters(fast=13, slow=25)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 7)) for i in range(120)]
    ind = make_ind(TSI, candles(closes))
    result = await ind.compute(TSI.Parameters(fast=13, slow=25))
    assert result is not None
    assert -100.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_fast_ge_slow_returns_none() -> None:
    closes = [float(100 + i) for i in range(120)]
    ind = make_ind(TSI, candles(closes))
    result = await ind.compute(TSI.Parameters(fast=25, slow=13))
    assert result is None


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i) for i in range(120)]
    ind = make_ind(TSI, candles(closes))
    result = await ind.compute(TSI.Parameters(fast=5, slow=10))
    assert result is not None
    assert result > 0
