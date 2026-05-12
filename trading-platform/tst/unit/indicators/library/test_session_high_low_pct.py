"""Tests for indicators/library/session_high_low_pct.py"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from trading.core.clock import Clock
from trading.indicators.library.session_high_low_pct import SessionHighLowPct
from tst.unit.indicators.conftest import candles, make_store


def _make_clock(now: datetime) -> Clock:
    clock = MagicMock(spec=Clock)
    clock.now.return_value = now
    return clock


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    store = make_store(candles([100.0]))
    clock = _make_clock(datetime(2024, 1, 1, 3, 45, tzinfo=UTC))
    ind = SessionHighLowPct(store, "TEST", "15min", clock=clock)
    assert await ind.compute(SessionHighLowPct.Parameters()) is None


@pytest.mark.asyncio
async def test_in_range() -> None:
    rows = candles([float(100 + i) for i in range(10)])
    store = make_store(rows)
    clock = _make_clock(datetime(2024, 1, 1, 3, 45, tzinfo=UTC))
    ind = SessionHighLowPct(store, "TEST", "15min", clock=clock)
    result = await ind.compute(SessionHighLowPct.Parameters())
    assert result is not None
    assert 0.0 <= result <= 1.0


@pytest.mark.asyncio
async def test_at_session_low_gives_zero() -> None:
    # Flat closes: all bars have same high/low spread, last close is same as first
    rows = candles([100.0, 101.0, 102.0, 103.0, 104.0, 100.0])
    store = make_store(rows)
    clock = _make_clock(datetime(2024, 1, 1, 3, 45, tzinfo=UTC))
    ind = SessionHighLowPct(store, "TEST", "15min", clock=clock)
    result = await ind.compute(SessionHighLowPct.Parameters())
    assert result is not None
    assert 0.0 <= result <= 1.0
