"""Tests for indicators/library/wilder_ema.py"""

from __future__ import annotations

import math
import pytest

from trading.indicators.library.wilder_ema import WilderEMA, wilder_ema
from tst.unit.indicators.conftest import candles, make_ind


def test_wilder_ema_fn_single_value() -> None:
    assert wilder_ema([100.0], period=1) == pytest.approx(100.0)


def test_wilder_ema_fn_constant_series() -> None:
    arr = [50.0] * 20
    for period in [3, 7, 14]:
        assert wilder_ema(arr, period) == pytest.approx(50.0, rel=1e-6)


def test_wilder_ema_fn_uptrend_lags() -> None:
    arr = list(range(1, 21))
    result = wilder_ema(arr, period=5)
    assert result < 20.0
    assert result > 10.0


@pytest.mark.asyncio
async def test_constant_series() -> None:
    ind = make_ind(WilderEMA, candles([100.0] * 20))
    result = await ind.compute(WilderEMA.Parameters(period=5))
    assert result is not None
    assert math.isclose(result, 100.0, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(WilderEMA, candles([100.0] * 3))
    assert await ind.compute(WilderEMA.Parameters(period=10)) is None


@pytest.mark.asyncio
async def test_uptrend_lags() -> None:
    closes = [float(100 + i) for i in range(30)]
    ind = make_ind(WilderEMA, candles(closes))
    result = await ind.compute(WilderEMA.Parameters(period=9))
    assert result is not None
    assert result < closes[-1]
