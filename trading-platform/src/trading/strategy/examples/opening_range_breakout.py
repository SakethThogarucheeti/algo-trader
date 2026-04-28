"""
Opening Range Breakout (ORB) Strategy.

Logic
-----
The Indian market (NSE) opens at 09:15 IST. The first ``orb_bars`` 15-minute
bars (09:15–10:15 for orb_bars=4) form the Opening Range (OR):
  - OR high = max(high) of those bars
  - OR low  = min(low)  of those bars

After the range is established, a breakout is signalled when close crosses
outside the range:

- BUY  when close > OR high  (upside breakout)
- SELL when close < OR low   (downside breakout)

Only one signal is taken per session (subsequent breakouts in the same
session are ignored). The range resets at the next session open.

Stop distance = ATR × atr_multiplier (from the bar triggering the signal).

Parameters
----------
orb_bars:
    Number of 15-minute bars that define the opening range (default 4 → 1 hour).
atr_period:
    ATR period for stop sizing (default 14).
atr_multiplier:
    ATR multiplier applied to stop distance (default 1.5).
interval_minutes:
    Bar duration in minutes — used to compute OR window end time (default 15).
"""

from __future__ import annotations

import logging
from datetime import time

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_IST_OFFSET_MINS = 5 * 60 + 30  # UTC+05:30
_SESSION_OPEN_IST = time(9, 15)

_DEFAULT_ORB_BARS = 4  # 4 × 15min = 1-hour opening range
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_ATR_MULTIPLIER = 1.5
_DEFAULT_INTERVAL_MINUTES = 15


class OpeningRangeBreakoutStrategy(Strategy):
    """
    Trade the first breakout beyond the session's opening range.

    State is maintained per symbol so concurrent symbols don't interfere.
    """

    def __init__(
        self,
        orb_bars: int = _DEFAULT_ORB_BARS,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        atr_multiplier: float = _DEFAULT_ATR_MULTIPLIER,
        interval_minutes: int = _DEFAULT_INTERVAL_MINUTES,
    ) -> None:
        if orb_bars < 1:
            raise ValueError(f"orb_bars must be ≥ 1, got {orb_bars}")
        self._orb_bars = orb_bars
        self._atr_col = f"atr_{atr_period}"
        self._atr_multiplier = atr_multiplier
        self._interval_minutes = interval_minutes

        # Per-symbol state: (session_date, or_high, or_low, signal_taken)
        self._state: dict[str, tuple[object, float, float, bool]] = {}

    @property
    def id(self) -> str:
        return "opening_range_breakout"

    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        if df.height < self._orb_bars + 1:
            return None

        if self._atr_col not in df.columns:
            logger.debug("ORB[%s]: missing column %r", symbol, self._atr_col)
            return None

        last = df.tail(1)
        if last[self._atr_col].is_null().any() or last[self._atr_col].is_nan().any():
            return None

        cur_ts = last["timestamp"][0]
        # Convert to IST
        ist_total_mins = (cur_ts.hour * 60 + cur_ts.minute + _IST_OFFSET_MINS) % (24 * 60)
        ist_hour = ist_total_mins // 60
        ist_min = ist_total_mins % 60
        cur_ist = time(ist_hour, ist_min)
        cur_date = cur_ts.date()

        session_open_min = _SESSION_OPEN_IST.hour * 60 + _SESSION_OPEN_IST.minute
        or_end_min = session_open_min + self._orb_bars * self._interval_minutes
        or_end_ist = time(or_end_min // 60, or_end_min % 60)

        # Reset state at session open
        state = self._state.get(symbol)
        if state is None or state[0] != cur_date:
            # New session — no signal yet
            self._state[symbol] = (cur_date, 0.0, float("inf"), False)
            state = self._state[symbol]

        session_date, or_high, or_low, signal_taken = state

        # --- Still within opening range window: accumulate range ---
        if cur_ist < or_end_ist:
            # Update OR bounds from this bar
            bar_high = float(last["high"][0])
            bar_low = float(last["low"][0])
            new_high = max(or_high, bar_high)
            new_low = min(or_low, bar_low)
            self._state[symbol] = (cur_date, new_high, new_low, False)
            logger.debug(
                "ORB[%s]: accumulating OR  bar_time=%s  OR=[%.2f, %.2f]",
                symbol,
                cur_ist,
                new_low,
                new_high,
            )
            return None

        # --- After range window: look for breakout ---
        if signal_taken:
            return None  # one signal per session

        if or_high == 0.0 or or_low == float("inf"):
            # Range never established (e.g. data gap at open)
            return None

        cur_close = float(last["close"][0])
        atr = float(last[self._atr_col][0])
        if atr <= 0:
            return None

        stop_distance = self._atr_multiplier * atr

        if cur_close > or_high:
            self._state[symbol] = (cur_date, or_high, or_low, True)
            logger.info(
                "ORB[%s]: BUY breakout  close=%.2f > OR_high=%.2f  stop=%.4f",
                symbol,
                cur_close,
                or_high,
                stop_distance,
            )
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                side=Side.BUY,
                strategy_id=self.id,
                signal_type=SignalType.ENTRY,
                stop_distance=stop_distance,
            )

        if cur_close < or_low:
            self._state[symbol] = (cur_date, or_high, or_low, True)
            logger.info(
                "ORB[%s]: SELL breakout close=%.2f < OR_low=%.2f  stop=%.4f",
                symbol,
                cur_close,
                or_low,
                stop_distance,
            )
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                side=Side.SELL,
                strategy_id=self.id,
                signal_type=SignalType.ENTRY,
                stop_distance=stop_distance,
            )

        return None
