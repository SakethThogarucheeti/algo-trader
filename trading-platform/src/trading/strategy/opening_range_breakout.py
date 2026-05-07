"""Opening Range Breakout (ORB) Strategy."""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

from trading.core.schemas import CandleEvent, InstrumentType, Side, SignalType
from trading.indicators.library.atr import ATR
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_IST_OFFSET_MINS = 5 * 60 + 30
_SESSION_OPEN_IST = time(9, 15)


class OpeningRangeBreakoutStrategy(Strategy):
    """
    Trade the first breakout beyond the session's opening range.

    The first orb_bars × interval_minutes of each session define the
    Opening Range (OR). A BUY signal fires when close breaks above OR high;
    SELL when close breaks below OR low. One signal per session.
    Stop distance = ATR × atr_multiplier.
    """

    alias = "opening_range_breakout"

    def __init__(
        self,
        orb_bars: int = 4,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        interval_minutes: int = 15,
    ) -> None:
        if orb_bars < 1:
            raise ValueError(f"orb_bars must be >= 1, got {orb_bars}")
        self._orb_bars = orb_bars
        self._atr_period = atr_period
        self._atr_multiplier = atr_multiplier
        self._interval_minutes = interval_minutes
        self._store: Any = None
        # indicator cache: symbol → atr
        self._inds: dict[str, ATR] = {}
        # (session_date, or_high, or_low, signal_taken)
        self._state: dict[str, tuple[object, float, float, bool]] = {}

    def set_store(self, store: Any) -> None:
        self._store = store

    def _get_atr(self, symbol: str, interval: str) -> ATR:
        if symbol not in self._inds:
            self._inds[symbol] = ATR(self._store, symbol, interval)
        return self._inds[symbol]

    def get_state(self) -> dict[str, object]:
        return {}

    async def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        candle: CandleEvent,
    ) -> Signal | None:
        atr_ind = self._get_atr(symbol, candle.interval)
        atr = await atr_ind.compute(ATR.Parameters(period=self._atr_period))
        if atr is None or atr <= 0:
            return None

        ts = candle.timestamp
        ist_total_mins = (ts.hour * 60 + ts.minute + _IST_OFFSET_MINS) % (24 * 60)
        ist_hour, ist_min = divmod(ist_total_mins, 60)
        cur_ist = time(ist_hour, ist_min)
        cur_date = ts.date()

        session_open_min = _SESSION_OPEN_IST.hour * 60 + _SESSION_OPEN_IST.minute
        or_end_min = session_open_min + self._orb_bars * self._interval_minutes
        or_end_ist = time(or_end_min // 60, or_end_min % 60)

        state = self._state.get(symbol)
        if state is None or state[0] != cur_date:
            self._state[symbol] = (cur_date, 0.0, float("inf"), False)
            state = self._state[symbol]

        session_date, or_high, or_low, signal_taken = state

        if cur_ist < or_end_ist:
            new_high = max(or_high, candle.high)
            new_low = min(or_low, candle.low)
            self._state[symbol] = (cur_date, new_high, new_low, False)
            return None

        if signal_taken or or_high == 0.0 or or_low == float("inf"):
            return None

        stop_distance = self._atr_multiplier * atr

        if candle.close > or_high:
            self._state[symbol] = (cur_date, or_high, or_low, True)
            logger.info("ORB[%s]: BUY  close=%.2f > OR_high=%.2f stop=%.4f",
                        symbol, candle.close, or_high, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.BUY, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        if candle.close < or_low:
            self._state[symbol] = (cur_date, or_high, or_low, True)
            logger.info("ORB[%s]: SELL close=%.2f < OR_low=%.2f stop=%.4f",
                        symbol, candle.close, or_low, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.SELL, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        return None
