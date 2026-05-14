"""Tests for indicators/library/pivot.py"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.pivot import PivotPoints
from trading.indicators.store import CandleStore


def _store(rows):
    s = MagicMock(spec=CandleStore)
    s.fetch = AsyncMock(return_value=rows)
    s.fetch_since = AsyncMock(return_value=rows)
    return s


@pytest.mark.asyncio
async def test_returns_none_single_bar() -> None:
    rows = [
        {
            "symbol": "X",
            "interval": "1day",
            "ts": datetime(2024, 1, 1, tzinfo=UTC),
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000,
        }
    ]
    ind = PivotPoints(_store(rows), "X", "1day")
    assert await ind.compute(PivotPoints.Parameters()) is None


@pytest.mark.asyncio
async def test_full_levels() -> None:
    rows = [
        {
            "symbol": "X",
            "interval": "1day",
            "ts": datetime(2024, 1, 1, tzinfo=UTC),
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 100.0,
            "volume": 1000,
        },
        {
            "symbol": "X",
            "interval": "1day",
            "ts": datetime(2024, 1, 2, tzinfo=UTC),
            "open": 101.0,
            "high": 112.0,
            "low": 92.0,
            "close": 105.0,
            "volume": 1000,
        },
    ]
    ind = PivotPoints(_store(rows), "X", "1day")
    result = await ind.compute_full(PivotPoints.Parameters())
    assert result is not None
    pp, r1, s1, r2, s2, r3, s3 = result
    assert math.isclose(pp, 100.0, rel_tol=1e-9)
    assert r1 > pp > s1
    assert r2 > r1
    assert s2 < s1
