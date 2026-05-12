"""Tests for indicators/library/vwap_bands.py"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from trading.core.clock import Clock
from trading.indicators.library.vwap_bands import VWAPBands
from tst.unit.indicators.conftest import candles, make_store


def _make_clock(now: datetime) -> Clock:
    clock = MagicMock(spec=Clock)
    clock.now.return_value = now
    return clock


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    store = make_store(candles([100.0]))
    # IST 09:15 = UTC 03:45
    clock = _make_clock(datetime(2024, 1, 1, 3, 45, tzinfo=UTC))
    ind = VWAPBands(store, "TEST", "15min", clock=clock)
    assert await ind.compute(VWAPBands.Parameters()) is None


@pytest.mark.asyncio
async def test_returns_float() -> None:
    rows = candles([float(100 + i) for i in range(10)])
    store = make_store(rows)
    clock = _make_clock(datetime(2024, 1, 1, 3, 45, tzinfo=UTC))
    ind = VWAPBands(store, "TEST", "15min", clock=clock)
    result = await ind.compute(VWAPBands.Parameters(num_std=2.0))
    assert result is not None
    assert isinstance(result, float)
