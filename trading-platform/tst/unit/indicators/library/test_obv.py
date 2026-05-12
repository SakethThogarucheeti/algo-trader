"""Tests for indicators/library/obv.py"""

from __future__ import annotations

import math

import pytest

from trading.indicators.library.obv import OBV
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(OBV, candles([100.0]))
    assert await ind.compute(OBV.Parameters(period=5)) is None


@pytest.mark.asyncio
async def test_accumulates_on_rising() -> None:
    closes = [100.0, 101.0, 102.0, 103.0, 104.0]
    ind = make_ind(OBV, candles(closes))
    result = await ind.compute(OBV.Parameters(period=5))
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_flat_is_zero() -> None:
    ind = make_ind(OBV, candles([100.0] * 5))
    result = await ind.compute(OBV.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)
