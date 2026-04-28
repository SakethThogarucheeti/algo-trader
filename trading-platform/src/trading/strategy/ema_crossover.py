from __future__ import annotations

import logging

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_DEFAULT_FAST = 9
_DEFAULT_SLOW = 21
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_ATR_MULTIPLIER = 1.5


class EmaCrossoverStrategy(Strategy):
    """
    Configurable EMA crossover strategy.

    Parameters
    ----------
    fast:
        Period of the fast EMA (default 9).
    slow:
        Period of the slow EMA (default 21). Must be > fast.
    atr_period:
        ATR smoothing period (default 14).
    atr_multiplier:
        Multiplier applied to ATR to compute stop_distance (default 1.5).

    Rules
    -----
    - BUY  when fast EMA crosses **above** slow EMA.
    - SELL when fast EMA crosses **below** slow EMA.
    - ``stop_distance = atr_multiplier × ATR(atr_period)`` (last bar).
    - Returns ``None`` if:
        - DataFrame has fewer than 2 rows (can't detect a crossover).
        - Any required indicator column is missing or null/NaN on the last two rows.
        - ATR is 0 or negative (stop distance would be zero — reject).
    """

    alias = "ema_crossover"

    def __init__(
        self,
        fast: int = _DEFAULT_FAST,
        slow: int = _DEFAULT_SLOW,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        atr_multiplier: float = _DEFAULT_ATR_MULTIPLIER,
    ) -> None:
        if fast >= slow:
            raise ValueError(f"fast ({fast}) must be less than slow ({slow})")
        self._fast = fast
        self._slow = slow
        self._atr_period = atr_period
        self._atr_multiplier = atr_multiplier

        self._fast_col = f"ema_{fast}"
        self._slow_col = f"ema_{slow}"
        self._atr_col = f"atr_{atr_period}"

        # Live state — updated after each candle for dashboard visibility
        self._last_fast: float | None = None
        self._last_slow: float | None = None
        self._last_atr: float | None = None
        self._last_close: float | None = None

    def get_state(self) -> dict[str, object]:
        return {
            f"ema_{self._fast}": round(self._last_fast, 4) if self._last_fast is not None else None,
            f"ema_{self._slow}": round(self._last_slow, 4) if self._last_slow is not None else None,
            f"atr_{self._atr_period}": round(self._last_atr, 4) if self._last_atr is not None else None,
            "last_close": round(self._last_close, 4) if self._last_close is not None else None,
        }

    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        if df.height < 2:
            logger.debug("EmaCrossover[%s]: insufficient rows (%d < 2)", symbol, df.height)
            return None

        last2 = df.tail(2)

        # Guard: required columns must be present and non-null on both rows
        for col in (self._fast_col, self._slow_col, self._atr_col):
            if col not in last2.columns:
                logger.debug("EmaCrossover[%s]: missing column %r", symbol, col)
                return None
            if last2[col].is_null().any() or last2[col].is_nan().any():
                logger.debug("EmaCrossover[%s]: null/NaN in %r — skipping bar", symbol, col)
                return None

        prev_fast = last2[self._fast_col][0]
        prev_slow = last2[self._slow_col][0]
        cur_fast = last2[self._fast_col][1]
        cur_slow = last2[self._slow_col][1]
        atr = last2[self._atr_col][1]

        # Update live state for dashboard
        self._last_fast = float(cur_fast)
        self._last_slow = float(cur_slow)
        self._last_atr = float(atr) if atr is not None else None
        self._last_close = float(df["close"][-1])

        # Guard: ATR must be a positive number
        if atr is None or atr <= 0:
            logger.debug("EmaCrossover[%s]: ATR=%s invalid — skipping", symbol, atr)
            return None

        stop_distance = self._atr_multiplier * atr

        # BUY crossover: fast EMA was below slow, now above
        if prev_fast < prev_slow and cur_fast > cur_slow:
            logger.info(
                "EmaCrossover[%s]: BUY signal  fast=%.4f→%.4f  slow=%.4f→%.4f  stop=%.4f",
                symbol,
                prev_fast,
                cur_fast,
                prev_slow,
                cur_slow,
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

        # SELL crossover: fast EMA was above slow, now below
        if prev_fast > prev_slow and cur_fast < cur_slow:
            logger.info(
                "EmaCrossover[%s]: SELL signal fast=%.4f→%.4f  slow=%.4f→%.4f  stop=%.4f",
                symbol,
                prev_fast,
                cur_fast,
                prev_slow,
                cur_slow,
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
