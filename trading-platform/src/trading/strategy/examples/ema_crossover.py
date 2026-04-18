from __future__ import annotations

import logging

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_ATR_MULTIPLIER = 1.5


class EmaCrossoverStrategy(Strategy):
    """
    EMA-9 / EMA-21 crossover strategy.

    Rules
    -----
    - BUY signal when EMA-9 crosses **above** EMA-21 (prev bar: 9 < 21, cur bar: 9 > 21).
    - SELL signal when EMA-9 crosses **below** EMA-21 (prev bar: 9 > 21, cur bar: 9 < 21).
    - ``stop_distance = 1.5 × ATR-14`` (last bar).
    - Returns ``None`` if:
        - DataFrame has fewer than 2 rows (can't detect a crossover).
        - Any of {ema_9, ema_21, atr_14} are null/NaN on the last two rows.
        - ATR-14 is 0 (stop distance would be zero — reject).
    """

    @property
    def id(self) -> str:
        return "ema_crossover"

    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        if df.height < 2:
            return None

        last2 = df.tail(2)

        # Guard: required columns must be present and non-null on both rows
        for col in ("ema_9", "ema_21", "atr_14"):
            if col not in last2.columns:
                return None
            if last2[col].is_null().any() or last2[col].is_nan().any():
                return None

        prev_9 = last2["ema_9"][0]
        prev_21 = last2["ema_21"][0]
        cur_9 = last2["ema_9"][1]
        cur_21 = last2["ema_21"][1]
        atr = last2["atr_14"][1]

        # Guard: ATR must be a positive number
        if atr is None or atr <= 0:
            return None

        stop_distance = _ATR_MULTIPLIER * atr

        # BUY crossover: ema_9 was below ema_21, now above
        if prev_9 < prev_21 and cur_9 > cur_21:
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                side=Side.BUY,
                strategy_id=self.id,
                signal_type=SignalType.ENTRY,
                stop_distance=stop_distance,
            )

        # SELL crossover: ema_9 was above ema_21, now below
        if prev_9 > prev_21 and cur_9 < cur_21:
            return Signal(
                symbol=symbol,
                instrument_type=instrument_type,
                side=Side.SELL,
                strategy_id=self.id,
                signal_type=SignalType.ENTRY,
                stop_distance=stop_distance,
            )

        return None
