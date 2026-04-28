"""
RSI Mean-Reversion Strategy.

Logic
-----
- BUY  when RSI was below *oversold* threshold on the previous bar and has
       crossed back above it on the current bar (momentum reverting upward).
- SELL when RSI was above *overbought* threshold on the previous bar and has
       crossed back below it on the current bar (momentum reverting downward).

Stop distance = ATR × atr_multiplier.

This is a counter-trend strategy suited to choppy / range-bound markets.
It performs poorly in sustained trending regimes.

Parameters
----------
rsi_period:
    RSI lookback period (default 14).
oversold:
    RSI level below which a position is considered oversold (default 30).
overbought:
    RSI level above which a position is considered overbought (default 70).
atr_period:
    ATR smoothing period for stop sizing (default 14).
atr_multiplier:
    ATR multiplier for stop distance (default 1.5).
"""

from __future__ import annotations

import logging

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_DEFAULT_RSI_PERIOD = 14
_DEFAULT_OVERSOLD = 30.0
_DEFAULT_OVERBOUGHT = 70.0
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_ATR_MULTIPLIER = 1.5


class RsiMeanReversionStrategy(Strategy):
    """RSI mean-reversion: buy the oversold bounce, sell the overbought fade."""

    alias = "rsi_mean_reversion"

    def __init__(
        self,
        rsi_period: int = _DEFAULT_RSI_PERIOD,
        oversold: float = _DEFAULT_OVERSOLD,
        overbought: float = _DEFAULT_OVERBOUGHT,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        atr_multiplier: float = _DEFAULT_ATR_MULTIPLIER,
    ) -> None:
        if oversold >= overbought:
            raise ValueError(f"oversold ({oversold}) must be less than overbought ({overbought})")
        self._rsi_col = f"rsi_{rsi_period}"
        self._atr_col = f"atr_{atr_period}"
        self._oversold = oversold
        self._overbought = overbought
        self._atr_multiplier = atr_multiplier

    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        if df.height < 2:
            return None

        last2 = df.tail(2)

        for col in (self._rsi_col, self._atr_col):
            if col not in last2.columns:
                logger.debug("RsiMeanReversion[%s]: missing column %r", symbol, col)
                return None
            if last2[col].is_null().any() or last2[col].is_nan().any():
                return None

        prev_rsi = float(last2[self._rsi_col][0])
        cur_rsi = float(last2[self._rsi_col][1])
        atr = float(last2[self._atr_col][1])

        if atr <= 0:
            return None

        stop_distance = self._atr_multiplier * atr

        # BUY: RSI crossed back above oversold threshold (bounce signal)
        if prev_rsi < self._oversold and cur_rsi >= self._oversold:
            logger.info(
                "RsiMeanReversion[%s]: BUY signal  rsi=%.1f→%.1f  oversold=%.0f  stop=%.4f",
                symbol,
                prev_rsi,
                cur_rsi,
                self._oversold,
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

        # SELL: RSI crossed back below overbought threshold (fade signal)
        if prev_rsi > self._overbought and cur_rsi <= self._overbought:
            logger.info(
                "RsiMeanReversion[%s]: SELL signal rsi=%.1f→%.1f  overbought=%.0f  stop=%.4f",
                symbol,
                prev_rsi,
                cur_rsi,
                self._overbought,
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
