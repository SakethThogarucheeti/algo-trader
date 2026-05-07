"""VWAP Bands — session VWAP with standard deviation bands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import UTC, datetime, time, timedelta

import numpy as np
from pydantic import Field

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore

_SESSION_OPEN_IST = time(9, 15)
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _today_session_open_utc(now: datetime) -> datetime:
    ist_now = now + _IST_OFFSET
    return (
        datetime(
            ist_now.year, ist_now.month, ist_now.day,
            _SESSION_OPEN_IST.hour, _SESSION_OPEN_IST.minute,
            tzinfo=UTC,
        )
        - _IST_OFFSET
    )


class VWAPBands(Indicator):
    """
    VWAP Bands — like Bollinger Bands but anchored to the session VWAP.

    Upper = VWAP + num_std * std(close - VWAP)
    Lower = VWAP - num_std * std(close - VWAP)
    %B    = (close - lower) / (upper - lower)

    Returns %B in [0, 1] approximately; > 1 or < 0 possible on extremes.
    Returns None if session has < 2 bars or upper == lower.
    """

    class Parameters(IndicatorParameters):
        num_std: float = Field(default=2.0, gt=0)

    alias = "vwap_bands"

    def __init__(self, store: CandleStore, symbol: str, interval: str, clock: Clock = SYSTEM_CLOCK) -> None:
        super().__init__(store, symbol, interval)
        self._clock = clock

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        since = _today_session_open_utc(self._clock.now())
        rows = await self._store.fetch_since(self._symbol, self._interval, since)
        if len(rows) < 2:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        volumes = np.array([r["volume"] for r in rows], dtype=float)

        total_vol = float(volumes.sum())
        if total_vol == 0.0:
            return None

        vwap = float((closes * volumes).sum() / total_vol)
        deviations = closes - vwap
        std = float(np.std(deviations, ddof=1))

        if std == 0.0:
            return None

        upper = vwap + params.num_std * std
        lower = vwap - params.num_std * std
        band_width = upper - lower
        if band_width == 0.0:
            return None

        return (closes[-1] - lower) / band_width

    def __repr__(self) -> str:
        return "VWAPBands()"
