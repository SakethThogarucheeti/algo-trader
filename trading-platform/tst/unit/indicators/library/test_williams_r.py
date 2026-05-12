"""Tests for indicators/library/williams_r.py"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.williams_r import WilliamsR
from trading.indicators.store import CandleStore
from tst.unit.indicators.conftest import candles, make_ind


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(WilliamsR, candles([100.0] * 5))
    assert await ind.compute(WilliamsR.Parameters(period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 10)) for i in range(14)]
    ind = make_ind(WilliamsR, candles(closes))
    result = await ind.compute(WilliamsR.Parameters(period=14))
    assert result is not None
    assert -100.0 <= result <= 0.0


@pytest.mark.asyncio
async def test_at_high_is_zero() -> None:
    rows = candles([100.0] * 14)
    for r in rows:
        r["high"] = 110.0
        r["low"] = 90.0
    rows[-1]["close"] = 110.0
    ind = WilliamsR(_store(rows), "TEST", "15min")
    result = await ind.compute(WilliamsR.Parameters(period=14))
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)
