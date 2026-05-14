"""Tests for indicators/library/stochastic.py"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.stochastic import Stochastic
from trading.indicators.store import CandleStore
from tst.unit.indicators.conftest import candles, make_ind


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(Stochastic, candles([100.0] * 5))
    assert await ind.compute(Stochastic.Parameters(k_period=14)) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    closes = [float(100 + (i % 10)) for i in range(30)]
    ind = make_ind(Stochastic, candles(closes))
    result = await ind.compute(Stochastic.Parameters(k_period=14, d_period=3))
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_at_high_is_100() -> None:
    rows = candles([100.0] * 13 + [110.0])
    for r in rows:
        r["high"] = r["close"] + 0.0
        r["low"] = r["close"] - 5.0
    rows[-1]["high"] = 110.0
    rows[-1]["low"] = 105.0
    ind = Stochastic(_store(rows), "TEST", "15min")
    result = await ind.compute(Stochastic.Parameters(k_period=14, d_period=3))
    assert result is not None
    assert result == pytest.approx(100.0, abs=1e-6)
