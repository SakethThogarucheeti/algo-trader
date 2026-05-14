"""Tests for indicators/library/true_range.py"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from trading.indicators.library.true_range import TrueRange, true_range
from trading.indicators.store import CandleStore


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


def test_fn_no_gaps() -> None:
    highs = np.array([110.0, 115.0, 108.0])
    lows = np.array([100.0, 105.0, 98.0])
    closes = np.array([105.0, 110.0, 103.0])
    tr = true_range(highs, lows, closes)
    assert tr[0] == pytest.approx(10.0)
    assert tr[1] == pytest.approx(10.0)
    assert tr[2] == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_no_gaps() -> None:
    rows = [
        {
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 100,
            "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
        },
        {
            "open": 11.0,
            "high": 13.0,
            "low": 10.0,
            "close": 12.0,
            "volume": 100,
            "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        },
    ]
    ind = TrueRange(_store(rows), "X", "1min")
    result = await ind.compute(TrueRange.Parameters())
    assert result is not None
    assert math.isclose(result, 3.0, rel_tol=1e-9)


@pytest.mark.asyncio
async def test_returns_none_single_bar() -> None:
    rows = [
        {
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 100,
            "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
        }
    ]
    ind = TrueRange(_store(rows), "X", "1min")
    assert await ind.compute(TrueRange.Parameters()) is None


@pytest.mark.asyncio
async def test_gap_up() -> None:
    rows = [
        {
            "open": 9.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": 100,
            "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
        },
        {
            "open": 13.0,
            "high": 15.0,
            "low": 12.0,
            "close": 14.0,
            "volume": 100,
            "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
        },
    ]
    ind = TrueRange(_store(rows), "X", "1min")
    result = await ind.compute(TrueRange.Parameters())
    assert result is not None
    assert math.isclose(result, 5.0, rel_tol=1e-9)
