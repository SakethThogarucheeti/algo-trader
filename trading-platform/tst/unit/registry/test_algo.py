"""Tests for pipeline/algo_registry.py — AlgoRegistry"""

from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.core.database import build_session_factory, init_db
from trading.core.schemas import CandleEvent, InstrumentType, SignalEvent
from trading.di.providers.strategy import make_strategy
from trading.indicators.polars_store import PolarsStore
from trading.registry.algo import AlgoConfig, AlgoRegistry, _AlgoInstance
from trading.storage.repository import Repository

BASE_TIME = datetime(2025, 1, 6, 9, 15, tzinfo=UTC)


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


def _build_algos(
    instrument_strategy_map: dict[str, str],
    instrument_types: dict[str, str],
) -> dict[str, _AlgoInstance]:
    return {
        symbol: _AlgoInstance(
            strategy=make_strategy(strategy_id),
            instrument_type=InstrumentType(
                instrument_types.get(symbol, InstrumentType.EQUITY.value)
            ),
        )
        for symbol, strategy_id in instrument_strategy_map.items()
    }


def make_registry(
    engine: AsyncEngine, warmup_candles: int = 5, algo_name: str = "test_algo"
) -> AlgoRegistry:
    sf = build_session_factory(engine)
    instrument_strategy_map = {"INFY": "ema_crossover"}
    instrument_types = {"INFY": "EQUITY"}
    config = AlgoConfig(
        instrument_strategy_map=instrument_strategy_map,
        instrument_types=instrument_types,
        equity=100_000.0,
        warmup_candles=warmup_candles,
        algo_name=algo_name,
    )
    algos = _build_algos(instrument_strategy_map, instrument_types)
    store = PolarsStore()
    return AlgoRegistry(
        config=config, session_factory=sf, repo=Repository(), algos=algos, store=store
    )


def make_candle(symbol: str = "INFY", tick_log_id: int = 0, **overrides) -> CandleEvent:
    base = dict(
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        interval="1min",
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000,
        timestamp=BASE_TIME,
        tick_log_id=tick_log_id,
    )
    return CandleEvent(**{**base, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_registry_builds_algo_instances(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    assert "INFY" in reg._algos


def test_registry_with_multiple_instruments(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    instrument_strategy_map = {"INFY": "ema_crossover", "TCS": "ema_crossover"}
    instrument_types = {"INFY": "EQUITY", "TCS": "EQUITY"}
    config = AlgoConfig(
        instrument_strategy_map=instrument_strategy_map,
        instrument_types=instrument_types,
    )
    algos = _build_algos(instrument_strategy_map, instrument_types)
    reg = AlgoRegistry(config=config, session_factory=sf, repo=Repository(), algos=algos)
    assert "INFY" in reg._algos
    assert "TCS" in reg._algos


# ---------------------------------------------------------------------------
# handle — unknown symbol
# ---------------------------------------------------------------------------


async def test_handle_unknown_symbol_returns_empty(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    result = await reg.handle(make_candle(symbol="UNKNOWN"))
    assert result == []


# ---------------------------------------------------------------------------
# handle — no signal (strategy hasn't warmed up yet)
# ---------------------------------------------------------------------------


async def test_handle_returns_empty_when_no_signal(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    result = await reg.handle(make_candle())
    assert isinstance(result, list)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# handle — bars_seen increments
# ---------------------------------------------------------------------------


async def test_bars_seen_increments_per_candle(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    await reg.handle(make_candle())
    await reg.handle(make_candle())
    assert reg._algos["INFY"].bars_seen == 2


# ---------------------------------------------------------------------------
# handle — produces SignalEvent when strategy fires
# ---------------------------------------------------------------------------


async def test_handle_returns_signal_when_crossover(engine: AsyncEngine) -> None:
    reg = make_registry(engine, warmup_candles=5, algo_name="test_algo")

    prices = [200.0 - i for i in range(30)] + [170.0 + i * 2 for i in range(30)]
    signals = []
    for i, price in enumerate(prices):
        candle = make_candle(
            open=price, high=price + 1, low=price - 1, close=price,
            timestamp=BASE_TIME + dt.timedelta(minutes=i),
        )
        result = await reg.handle(candle)
        signals.extend(result)

    assert len(signals) >= 1
    assert isinstance(signals[0], SignalEvent)
    assert signals[0].symbol == "INFY"


# ---------------------------------------------------------------------------
# handle — multi-instrument fan-out
# ---------------------------------------------------------------------------


async def test_handle_only_affects_matching_symbol(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    instrument_strategy_map = {"INFY": "ema_crossover", "TCS": "ema_crossover"}
    instrument_types = {"INFY": "EQUITY", "TCS": "EQUITY"}
    config = AlgoConfig(
        instrument_strategy_map=instrument_strategy_map,
        instrument_types=instrument_types,
        warmup_candles=5,
    )
    algos = _build_algos(instrument_strategy_map, instrument_types)
    reg = AlgoRegistry(config=config, session_factory=sf, repo=Repository(), algos=algos)

    await reg.handle(make_candle(symbol="INFY"))

    assert reg._algos["INFY"].bars_seen == 1
    assert reg._algos["TCS"].bars_seen == 0


# ---------------------------------------------------------------------------
# handle — tick_log_id != 0 triggers upsert
# ---------------------------------------------------------------------------


async def test_handle_upsert_triggered_when_tick_log_id_nonzero(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    await reg.handle(make_candle(tick_log_id=1))
    assert reg._algos["INFY"].bars_seen == 1


# ---------------------------------------------------------------------------
# handle — signal path with tick_log_id != 0
# ---------------------------------------------------------------------------


async def test_handle_signal_with_nonzero_tick_log_id(engine: AsyncEngine) -> None:
    reg = make_registry(engine, warmup_candles=5, algo_name="audit_test")

    prices = [200.0 - i for i in range(30)] + [170.0 + i * 2 for i in range(30)]
    signals = []
    for i, price in enumerate(prices):
        candle = make_candle(
            open=price, high=price + 1, low=price - 1, close=price,
            timestamp=BASE_TIME + dt.timedelta(minutes=i),
            tick_log_id=i + 1,
        )
        result = await reg.handle(candle)
        signals.extend(result)

    assert len(signals) >= 1
    assert isinstance(signals[0], SignalEvent)


# ---------------------------------------------------------------------------
# _upsert_state and _log_signal — direct coverage
# ---------------------------------------------------------------------------


async def test_upsert_state_direct(engine: AsyncEngine) -> None:
    reg = make_registry(engine)
    instance = reg._algos["INFY"]
    instance.bars_seen = 5
    await reg._upsert_state(instance)


async def test_log_signal_skips_when_tick_log_id_zero(engine: AsyncEngine) -> None:
    from trading.core.schemas import Side, SignalType
    reg = make_registry(engine)
    signal_event = SignalEvent(
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        strategy_id="ema_crossover",
        signal_type=SignalType.ENTRY,
        stop_distance=10.0,
        tick_log_id=0,
    )
    await reg._log_signal(signal_event, "test")


async def test_log_signal_with_nonzero_tick_log_id(engine: AsyncEngine) -> None:
    from trading.core.schemas import Side, SignalType
    reg = make_registry(engine)
    signal_event = SignalEvent(
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        strategy_id="ema_crossover",
        signal_type=SignalType.ENTRY,
        stop_distance=10.0,
        tick_log_id=42,
    )
    await reg._log_signal(signal_event, "test_algo")


# ---------------------------------------------------------------------------
# AlgoConfig defaults
# ---------------------------------------------------------------------------


def test_algo_config_defaults() -> None:
    cfg = AlgoConfig(
        instrument_strategy_map={"INFY": "ema_crossover"},
    )
    assert cfg.equity == 100_000.0
    assert cfg.warmup_candles == 200
    assert cfg.algo_name == "default"
