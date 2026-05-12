"""Tests for indicators/library/rsi_divergence.py"""

from __future__ import annotations

import pytest

from trading.indicators.library.rsi_divergence import RSIDivergence
from tst.unit.indicators.conftest import candles, make_ind


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    ind = make_ind(RSIDivergence, candles([100.0] * 5))
    assert await ind.compute(RSIDivergence.Parameters(rsi_period=14, divergence_window=10)) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    closes = [float(100 + (i % 7)) for i in range(100)]
    ind = make_ind(RSIDivergence, candles(closes))
    result = await ind.compute(RSIDivergence.Parameters(rsi_period=14, divergence_window=10))
    assert result is not None
    assert isinstance(result, float)
