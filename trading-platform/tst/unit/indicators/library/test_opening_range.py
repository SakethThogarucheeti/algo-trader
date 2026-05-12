"""Tests for indicators/library/opening_range.py"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trading.indicators.library.opening_range import OpeningRangePosition
from tst.unit.indicators.conftest import make_ind


def _session_rows(n_bars: int, start_close: float = 100.0) -> list[dict]:
    base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    rows = []
    # Prior session (previous day)
    prev = base - timedelta(hours=16)
    rows.append({
        "symbol": "TEST", "interval": "15min",
        "ts": prev, "open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 1000,
    })
    # Current session
    for i in range(n_bars):
        c = start_close + i
        rows.append({
            "symbol": "TEST", "interval": "15min",
            "ts": base + timedelta(minutes=15 * i),
            "open": c, "high": c + 2.0, "low": c - 1.0, "close": c + 1.0, "volume": 1000,
        })
    return rows


@pytest.mark.asyncio
async def test_returns_none_insufficient() -> None:
    from tst.unit.indicators.conftest import candles
    ind = make_ind(OpeningRangePosition, candles([100.0] * 2))
    assert await ind.compute(OpeningRangePosition.Parameters(range_bars=4)) is None


@pytest.mark.asyncio
async def test_returns_float_in_range() -> None:
    rows = _session_rows(n_bars=10)
    ind = make_ind(OpeningRangePosition, rows)
    result = await ind.compute(OpeningRangePosition.Parameters(range_bars=4))
    assert result is not None
    assert isinstance(result, float)
