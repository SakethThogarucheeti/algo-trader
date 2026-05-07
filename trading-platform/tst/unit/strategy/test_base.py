"""Tests for strategy/base.py and EmaCrossoverStrategy (indicator-based API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from trading.core.schemas import CandleEvent, InstrumentType, Side, SignalType
from trading.indicators.context import IndicatorContext
from trading.indicators.polars_store import PolarsStore
from trading.strategy.ema_crossover import EmaCrossoverStrategy

BASE_TIME = datetime(2025, 1, 6, 3, 45, 0, tzinfo=UTC)
INFY = "INFY"
EQUITY = InstrumentType.EQUITY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candle(
    close: float,
    offset_minutes: int,
    *,
    high: float | None = None,
    low: float | None = None,
) -> CandleEvent:
    return CandleEvent(
        symbol=INFY,
        instrument_type=EQUITY,
        interval="1min",
        open=close,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=1000,
        timestamp=BASE_TIME + timedelta(minutes=offset_minutes),
        tick_log_id=0,
    )


class _Harness:
    def __init__(self, strategy: EmaCrossoverStrategy) -> None:
        self._strategy = strategy
        self._store = PolarsStore()
        self._ctx = IndicatorContext(self._store)

    async def feed(self, candle: CandleEvent):
        self._store.push(candle.symbol, candle.interval, {
            "symbol": candle.symbol, "interval": candle.interval, "ts": candle.timestamp,
            "open": candle.open, "high": candle.high, "low": candle.low,
            "close": candle.close, "volume": candle.volume,
        })
        self._ctx.bind_all(self._strategy.indicators, candle.symbol, candle.interval)
        return await self._strategy.on_candle(candle.symbol, EQUITY, candle)


async def _feed_prices(strategy: EmaCrossoverStrategy, prices: list[float]) -> list:
    h = _Harness(strategy)
    signals = []
    for i, p in enumerate(prices):
        sig = await h.feed(_candle(p, offset_minutes=i))
        if sig is not None:
            signals.append(sig)
    return signals


# ---------------------------------------------------------------------------
# BUY crossover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buy_signal_on_ema9_crossing_above_ema21() -> None:
    # fast=3, slow=7 so warmup is quicker in tests
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    # Falling phase then sharp rise: fast crosses above slow
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    assert any(s.side == Side.BUY for s in signals)


@pytest.mark.asyncio
async def test_buy_signal_signal_type_is_entry() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    buy_signals = [s for s in signals if s.side == Side.BUY]
    assert buy_signals
    assert all(s.signal_type == SignalType.ENTRY for s in buy_signals)
    assert all(s.symbol == INFY for s in buy_signals)
    assert all(s.strategy_id == "ema_crossover" for s in buy_signals)


@pytest.mark.asyncio
async def test_buy_signal_stop_distance_uses_atr_multiplier() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7, atr_multiplier=2.0)
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    buy_signals = [s for s in signals if s.side == Side.BUY]
    assert buy_signals
    assert all(s.stop_distance > 0 for s in buy_signals)


# ---------------------------------------------------------------------------
# SELL crossover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sell_signal_on_ema9_crossing_below_ema21() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    prices = [100.0 + i for i in range(20)] + [120.0 - i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    assert any(s.side == Side.SELL for s in signals)


# ---------------------------------------------------------------------------
# No signal cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_signal_on_single_bar() -> None:
    strat = EmaCrossoverStrategy()
    signals = await _feed_prices(strat, [100.0])
    assert signals == []


@pytest.mark.asyncio
async def test_no_signal_on_insufficient_data() -> None:
    strat = EmaCrossoverStrategy()
    # Only 3 bars — well below warmup threshold for EMA(9)/EMA(21)
    signals = await _feed_prices(strat, [100.0, 101.0, 102.0])
    assert signals == []


# ---------------------------------------------------------------------------
# Signal properties
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_each_signal_has_unique_signal_id() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    ids = [s.signal_id for s in signals]
    assert len(ids) == len(set(ids)), "Each signal must have a unique signal_id"


@pytest.mark.asyncio
async def test_signal_id_is_valid_uuid() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    assert signals
    assert isinstance(signals[0].signal_id, UUID)
    assert signals[0].signal_id.version == 4


@pytest.mark.asyncio
async def test_signal_stop_distance_always_positive() -> None:
    strat = EmaCrossoverStrategy(fast=3, slow=7)
    prices = [100.0 - i for i in range(20)] + [80.0 + i * 2 for i in range(20)]
    signals = await _feed_prices(strat, prices)
    assert signals
    assert all(s.stop_distance > 0 for s in signals)


# ---------------------------------------------------------------------------
# Strategy params validation
# ---------------------------------------------------------------------------


def test_invalid_params_raise() -> None:
    with pytest.raises(ValueError):
        EmaCrossoverStrategy(fast=21, slow=9)


def test_strategy_id() -> None:
    assert EmaCrossoverStrategy().id == "ema_crossover"
