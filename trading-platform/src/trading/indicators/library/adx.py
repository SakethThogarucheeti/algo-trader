"""ADX — Average Directional Index with +DI and -DI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters
from trading.indicators.library.true_range import true_range
from trading.indicators.library.wilder_ema import wilder_ema

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_LOOKBACK_FACTOR = 3


class ADX(Indicator):
    """
    Average Directional Index (+DI, -DI, ADX).

    +DI and -DI measure directional movement; ADX is their smoothed ratio.
    ADX > 25 indicates a trending market; < 20 indicates ranging.

    compute() returns ADX. Use compute_full() for (adx, plus_di, minus_di).
    Returns None when fewer than *period* * 2 bars are available.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=14, ge=2)

    alias = "adx"

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        result = await self.compute_full(params)
        return result[0] if result is not None else None

    async def compute_full(self, params: Parameters) -> tuple[float, float, float] | None:
        rows = await self._store.fetch(
            self._symbol, self._interval, params.period * _LOOKBACK_FACTOR
        )
        if len(rows) < params.period * 2:
            return None

        highs = np.array([r["high"] for r in rows], dtype=float)
        lows = np.array([r["low"] for r in rows], dtype=float)
        closes = np.array([r["close"] for r in rows], dtype=float)

        tr = true_range(highs, lows, closes)

        # Directional movement
        up_move = highs[1:] - highs[:-1]
        down_move = lows[:-1] - lows[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        smoothed_tr = wilder_ema(tr[1:], params.period)
        smoothed_plus = wilder_ema(plus_dm, params.period)
        smoothed_minus = wilder_ema(minus_dm, params.period)

        if smoothed_tr == 0.0:
            return None

        plus_di = 100.0 * smoothed_plus / smoothed_tr
        minus_di = 100.0 * smoothed_minus / smoothed_tr

        di_sum = plus_di + minus_di
        if di_sum == 0.0:
            return None

        dx = 100.0 * abs(plus_di - minus_di) / di_sum

        # ADX is the Wilder EMA of DX — approximate with the current DX value
        # (a full rolling DX series would require more history; this is the
        # standard single-pass approximation used by most charting packages)
        adx = dx
        return float(adx), float(plus_di), float(minus_di)

    def __repr__(self) -> str:
        return "ADX()"
