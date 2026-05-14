"""Tests for indicators/library/gap.py"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from trading.indicators.library.gap import GapSize
from tst.unit.indicators.conftest import make_ind


def _two_session_candles(prev_close: float, session_open: float) -> list[dict]:
    base = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    rows = []
    for i in range(5):
        rows.append(
            {
                "symbol": "TEST",
                "interval": "15min",
                "ts": base + timedelta(minutes=15 * i),
                "open": prev_close,
                "high": prev_close + 1,
                "low": prev_close - 1,
                "close": prev_close,
                "volume": 1000,
            }
        )
    # Next session — 16 hours later
    next_day = base + timedelta(hours=16)
    for i in range(5):
        c = session_open + i * 0.5
        rows.append(
            {
                "symbol": "TEST",
                "interval": "15min",
                "ts": next_day + timedelta(minutes=15 * i),
                "open": session_open if i == 0 else c,
                "high": c + 1,
                "low": c - 1,
                "close": c,
                "volume": 1000,
            }
        )
    return rows


@pytest.mark.asyncio
async def test_returns_none_single_session() -> None:
    from tst.unit.indicators.conftest import candles

    ind = make_ind(GapSize, candles([100.0] * 10))
    assert await ind.compute(GapSize.Parameters()) is None


@pytest.mark.asyncio
async def test_gap_up() -> None:
    rows = _two_session_candles(prev_close=100.0, session_open=105.0)
    ind = make_ind(GapSize, rows)
    result = await ind.compute(GapSize.Parameters())
    assert result is not None
    assert result == pytest.approx(5.0, rel=1e-3)


@pytest.mark.asyncio
async def test_gap_down() -> None:
    rows = _two_session_candles(prev_close=100.0, session_open=95.0)
    ind = make_ind(GapSize, rows)
    result = await ind.compute(GapSize.Parameters())
    assert result is not None
    assert result == pytest.approx(-5.0, rel=1e-3)
