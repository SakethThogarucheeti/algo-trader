"""VWAP Reversion Strategy."""

from __future__ import annotations

import logging
from typing import Any

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.core.schemas import CandleEvent, InstrumentType, Side, SignalType
from trading.indicators.library.atr import ATR
from trading.indicators.library.vwap import VWAP
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)


class VwapReversionStrategy(Strategy):
    """
    Mean-revert to session VWAP when price extends by N × ATR.

    BUY  when previous close was below VWAP by ≥ vwap_band × ATR and
         current close is higher than previous (momentum turning up).
    SELL when previous close was above VWAP by ≥ vwap_band × ATR and
         current close is lower than previous (momentum turning down).
    Stop distance = ATR × atr_multiplier.
    """

    alias = "vwap_reversion"

    def __init__(
        self,
        vwap_band: float = 1.0,
        atr_period: int = 14,
        atr_multiplier: float = 1.0,
        clock: Clock = SYSTEM_CLOCK,
    ) -> None:
        if vwap_band <= 0:
            raise ValueError(f"vwap_band must be positive, got {vwap_band}")
        self._vwap_band = vwap_band
        self._atr_period = atr_period
        self._atr_multiplier = atr_multiplier
        self._clock = clock
        self._store: Any = None
        # indicator cache: symbol → (vwap, atr)
        self._inds: dict[str, tuple[VWAP, ATR]] = {}
        self._prev_close: dict[str, float | None] = {}
        self._prev_vwap: dict[str, float | None] = {}
        # last computed values for dashboard state
        self._last_vwap: float | None = None
        self._last_atr: float | None = None
        self._last_close: float | None = None

    def set_store(self, store: Any) -> None:
        self._store = store

    def _get_inds(self, symbol: str, interval: str) -> tuple[VWAP, ATR]:
        if symbol not in self._inds:
            store = self._store
            self._inds[symbol] = (
                VWAP(store, symbol, interval, self._clock),
                ATR(store, symbol, interval),
            )
        return self._inds[symbol]

    def get_state(self) -> dict[str, object]:
        return {
            "vwap": round(self._last_vwap, 4) if self._last_vwap is not None else None,
            f"atr_{self._atr_period}": round(self._last_atr, 4) if self._last_atr is not None else None,
            "last_close": round(self._last_close, 2) if self._last_close is not None else None,
            "vwap_band": self._vwap_band,
        }

    async def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        candle: CandleEvent,
    ) -> Signal | None:
        vwap_ind, atr_ind = self._get_inds(symbol, candle.interval)
        vwap_params = VWAP.Parameters()
        atr_params = ATR.Parameters(period=self._atr_period)

        vwap = await vwap_ind.compute(vwap_params)
        atr = await atr_ind.compute(atr_params)

        self._last_vwap = vwap
        self._last_atr = atr
        self._last_close = float(candle.close)

        self.chart("price", "vwap", vwap, candle.timestamp)
        self.chart("oscillators", f"atr_{self._atr_period}", atr, candle.timestamp)

        prev_close = self._prev_close.get(symbol)
        prev_vwap = self._prev_vwap.get(symbol)
        self._prev_close[symbol] = candle.close
        self._prev_vwap[symbol] = vwap

        if vwap is None or atr is None or atr <= 0:
            return None
        if prev_close is None or prev_vwap is None:
            return None

        stop_distance = self._atr_multiplier * atr
        band = self._vwap_band * atr
        deviation = prev_close - prev_vwap

        if deviation <= -band and candle.close > prev_close:
            logger.info("VwapReversion[%s]: BUY  dev=%.2f atr=%.2f stop=%.4f",
                        symbol, deviation, atr, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.BUY, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        if deviation >= band and candle.close < prev_close:
            logger.info("VwapReversion[%s]: SELL dev=%.2f atr=%.2f stop=%.4f",
                        symbol, deviation, atr, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.SELL, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        return None
