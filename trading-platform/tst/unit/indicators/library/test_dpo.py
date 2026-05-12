"""Tests for indicators/library/dpo.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.dpo import DPO
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(DPO, candles([100.0] * 5))
    assert await ind.compute(DPO.Parameters(period=20)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + i) for i in range(40)]
    ind = make_ind(DPO, candles(closes))
    result = await ind.compute(DPO.Parameters(period=20))
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_uptrend_positive() -> None:
    closes = [float(100 + i * 2) for i in range(40)]
    ind = make_ind(DPO, candles(closes))
    result = await ind.compute(DPO.Parameters(period=20))
    assert result is not None
    assert result > 0
