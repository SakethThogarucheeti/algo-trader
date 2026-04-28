"""
Clock abstraction for live and simulated time.

Live trading uses ``SystemClock`` which delegates to ``datetime.now(UTC)``.
Backtesting uses ``SimulatedClock`` whose current time is advanced by the
CandlePlayer at each bar, so all components that call ``clock.now()`` see
the bar's timestamp rather than the wall clock.

Usage
-----
Inject the clock wherever ``datetime.now(UTC)`` was previously called::

    from trading.core.clock import Clock, SystemClock

    class MyComponent:
        def __init__(self, clock: Clock = SystemClock()):
            self._clock = clock

        def do_something(self):
            now = self._clock.now()

The singleton ``SYSTEM_CLOCK`` is available for convenience in production code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    """Abstract time provider."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...


class SystemClock(Clock):
    """Production clock — delegates to the OS."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock(Clock):
    """
    Simulated clock for backtesting.

    The current time is set externally (by CandlePlayer at each bar) via
    ``advance(ts)``. All components that use this clock will see the candle
    bar's timestamp instead of the wall clock.

    Starts at ``datetime.min`` (UTC) so any time check against it before
    the first ``advance()`` call is safely in the past.
    """

    def __init__(self) -> None:
        self._current: datetime = datetime.min.replace(tzinfo=UTC)

    def advance(self, ts: datetime) -> None:
        """Advance the clock to *ts*. Called by CandlePlayer at each bar."""
        self._current = ts

    def now(self) -> datetime:
        return self._current


# Singleton for convenience — production code can import this directly.
SYSTEM_CLOCK: Clock = SystemClock()
