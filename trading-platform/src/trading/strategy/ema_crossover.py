from __future__ import annotations

import logging
from typing import Any

from trading.core.schemas import CandleEvent, InstrumentType, Side, SignalType
from trading.indicators.library.atr import ATR
from trading.indicators.library.ema import EMA
from trading.strategy.base import Signal, Strategy

logger = logging.getLogger(__name__)

_DEFAULT_FAST = 9
_DEFAULT_SLOW = 21
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_ATR_MULTIPLIER = 1.5


class EmaCrossoverStrategy(Strategy):
    """
    EMA crossover strategy.

    BUY  when fast EMA crosses above slow EMA.
    SELL when fast EMA crosses below slow EMA.
    Stop distance = atr_multiplier × ATR.
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
        self._fast_period = fast
        self._slow_period = slow
        self._atr_period = atr_period
        self._atr_multiplier = atr_multiplier
        self._store: Any = None
        # indicator cache: symbol → (fast_ema, slow_ema, atr)
        self._inds: dict[str, tuple[EMA, EMA, ATR]] = {}
        self._prev_fast: dict[str, float | None] = {}
        self._prev_slow: dict[str, float | None] = {}

    def set_store(self, store: Any) -> None:
        self._store = store

    def _get_inds(self, symbol: str, interval: str) -> tuple[EMA, EMA, ATR]:
        if symbol not in self._inds:
            store = self._store
            self._inds[symbol] = (
                EMA(store, symbol, interval),
                EMA(store, symbol, interval),
                ATR(store, symbol, interval),
            )
        return self._inds[symbol]

    def get_state(self) -> dict[str, object]:
        return {}

    async def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        candle: CandleEvent,
    ) -> Signal | None:
        fast_ind, slow_ind, atr_ind = self._get_inds(symbol, candle.interval)
        fast_params = EMA.Parameters(period=self._fast_period)
        slow_params = EMA.Parameters(period=self._slow_period)
        atr_params = ATR.Parameters(period=self._atr_period)

        fast = await fast_ind.compute(fast_params)
        slow = await slow_ind.compute(slow_params)
        atr = await atr_ind.compute(atr_params)

        if fast is None or slow is None or atr is None or atr <= 0:
            self._prev_fast[symbol] = fast
            self._prev_slow[symbol] = slow
            return None

        prev_fast = self._prev_fast.get(symbol)
        prev_slow = self._prev_slow.get(symbol)
        self._prev_fast[symbol] = fast
        self._prev_slow[symbol] = slow

        if prev_fast is None or prev_slow is None:
            return None

        stop_distance = self._atr_multiplier * atr

        if prev_fast < prev_slow and fast > slow:
            logger.info("EmaCrossover[%s]: BUY  fast=%.4f→%.4f slow=%.4f→%.4f stop=%.4f",
                        symbol, prev_fast, fast, prev_slow, slow, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.BUY, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        if prev_fast > prev_slow and fast < slow:
            logger.info("EmaCrossover[%s]: SELL fast=%.4f→%.4f slow=%.4f→%.4f stop=%.4f",
                        symbol, prev_fast, fast, prev_slow, slow, stop_distance)
            return Signal(
                symbol=symbol, instrument_type=instrument_type,
                side=Side.SELL, strategy_id=self.id,
                signal_type=SignalType.ENTRY, stop_distance=stop_distance,
                timestamp=candle.timestamp,
            )

        return None
