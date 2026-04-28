"""
VWAP Reversion Strategy.

Logic
-----
Price tends to revert to the session VWAP (Volume-Weighted Average Price).
This strategy enters when price has moved a significant distance from VWAP
(measured in ATR multiples) and the most recent bar shows the move losing
momentum (close is moving back toward VWAP).

Entry conditions
~~~~~~~~~~~~~~~~
- BUY  when:
    1. Previous bar close was below VWAP by ≥ ``vwap_band`` × ATR (oversold vs VWAP).
    2. Current bar close is *higher* than previous bar close (momentum turning up).

- SELL when:
    1. Previous bar close was above VWAP by ≥ ``vwap_band`` × ATR (overbought vs VWAP).
    2. Current bar close is *lower* than previous bar close (momentum turning down).

Stop distance = ATR × atr_multiplier.

Parameters
----------
vwap_band:
    Number of ATR units away from VWAP required to trigger (default 1.0).
atr_period:
    ATR smoothing period (default 14).
atr_multiplier:
    ATR multiplier for stop sizing (default 1.0).
"""

from __future__ import annotations

import logging

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_DEFAULT_VWAP_BAND = 1.0
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_ATR_MULTIPLIER = 1.0


class VwapReversionStrategy(Strategy):
    """Mean-revert to session VWAP when price extends by N × ATR."""

    def __init__(
        self,
        vwap_band: float = _DEFAULT_VWAP_BAND,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        atr_multiplier: float = _DEFAULT_ATR_MULTIPLIER,
    ) -> None:
        if vwap_band <= 0:
            raise ValueError(f"vwap_band must be positive, got {vwap_band}")
        self._vwap_band = vwap_band
        self._atr_col = f"atr_{atr_period}"
        self._atr_multiplier = atr_multiplier

    @property
    def id(self) -> str:
        return "vwap_reversion"

    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        if df.height < 2:
            return None

        last2 = df.tail(2)

        for col in (self._atr_col, "vwap"):
            if col not in last2.columns:
                logger.debug("VwapReversion[%s]: missing column %r", symbol, col)
                return None
            if last2[col].is_null().any() or last2[col].is_nan().any():
                return None

        prev_close = float(last2["close"][0])
        cur_close = float(last2["close"][1])
        prev_vwap = float(last2["vwap"][0])
        atr = float(last2[self._atr_col][1])

        if atr <= 0:
            return None

        stop_distance = self._atr_multiplier * atr
        band = self._vwap_band * atr
        deviation = prev_close - prev_vwap  # positive → above VWAP, negative → below

        # BUY: price was below VWAP by ≥ band and is now turning up
        if deviation <= -band and cur_close > prev_close:
            logger.info(
                "VwapReversion[%s]: BUY signal  close=%.2f  vwap=%.2f"
                "  dev=%.2f  atr=%.2f  stop=%.4f",
                symbol,
                cur_close,
                prev_vwap,
                deviation,
                atr,
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

        # SELL: price was above VWAP by ≥ band and is now turning down
        if deviation >= band and cur_close < prev_close:
            logger.info(
                "VwapReversion[%s]: SELL signal close=%.2f  vwap=%.2f"
                "  dev=%.2f  atr=%.2f  stop=%.4f",
                symbol,
                cur_close,
                prev_vwap,
                deviation,
                atr,
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
