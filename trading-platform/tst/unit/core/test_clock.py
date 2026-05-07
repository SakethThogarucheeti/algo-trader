"""Tests for core/clock.py"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trading.core.clock import SYSTEM_CLOCK, Clock, SimulatedClock, SystemClock


def test_system_clock_returns_utc_datetime() -> None:
    sc = SystemClock()
    now = sc.now()
    assert now.tzinfo is not None
    assert now.tzinfo == UTC or str(now.tzinfo) == "UTC"


def test_system_clock_is_recent() -> None:
    sc = SystemClock()
    before = datetime.now(UTC)
    result = sc.now()
    after = datetime.now(UTC)
    assert before <= result <= after


def test_clock_is_abstract() -> None:
    with pytest.raises(TypeError):
        Clock()  # type: ignore[abstract]


def test_simulated_clock_starts_at_min() -> None:
    sc = SimulatedClock()
    assert sc.now() == datetime.min.replace(tzinfo=UTC)


def test_simulated_clock_advance() -> None:
    sc = SimulatedClock()
    ts = datetime(2025, 6, 1, 9, 15, tzinfo=UTC)
    sc.advance(ts)
    assert sc.now() == ts


def test_simulated_clock_advance_multiple_times() -> None:
    sc = SimulatedClock()
    t1 = datetime(2025, 1, 1, 9, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 1, 9, 5, tzinfo=UTC)
    sc.advance(t1)
    assert sc.now() == t1
    sc.advance(t2)
    assert sc.now() == t2


def test_system_clock_singleton_is_clock_instance() -> None:
    assert isinstance(SYSTEM_CLOCK, Clock)
    assert isinstance(SYSTEM_CLOCK, SystemClock)
