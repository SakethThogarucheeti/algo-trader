"""Tests for indicators/library/roc.py"""

from __future__ import annotations

import math

import pytest

from trading.indicators.library.roc import ROC
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(ROC, candles([100.0] * 5))
    assert await ind.compute(ROC.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_flat_is_zero() -> None:
    ind = make_ind(ROC, candles([100.0] * 6))
    result = await ind.compute(ROC.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_ten_percent_rise() -> None:
    ind = make_ind(ROC, candles([100.0, 110.0]))
    result = await ind.compute(ROC.Parameters(period=1))
    assert result is not None
    assert math.isclose(result, 10.0, rel_tol=1e-9)
