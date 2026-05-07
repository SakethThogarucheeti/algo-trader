"""Tests for thin lifecycle wrappers: AlgoRunner, RiskController, OrderExecutor"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.broker.base.broker import Broker
from trading.broker.paper_broker import PriceStore
from trading.core.database import build_session_factory, init_db
from trading.core.models import Instrument
from trading.engine.algo_runner import AlgoRunner
from trading.engine.candle_aggregator import CandleAggregator
from trading.engine.component import ComponentState
from trading.execution.executor import OrderExecutor
from trading.registry.algo import AlgoConfig, AlgoRegistry
from trading.registry.candle import CandleConfig, CandleRegistry
from trading.registry.exec import ExecConfig, ExecRegistry
from trading.registry.risk import RiskConfig, RiskRegistry
from trading.registry.tick import CircuitBreaker
from trading.risk.base import RiskController
from trading.storage.repository import Repository


class _StubBroker(Broker):
    def get_instruments(self) -> pl.DataFrame:
        return pl.DataFrame()

    def get_ohlc(self, symbol, interval, start, end) -> pl.DataFrame:  # type: ignore[override]
        return pl.DataFrame()

    async def place_order(self, symbol, side, qty, order_type, limit_price=None) -> str:  # type: ignore[override]
        return "STUB_001"


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


# ---------------------------------------------------------------------------
# AlgoRunner
# ---------------------------------------------------------------------------


async def test_algo_runner_starts_and_reaches_running(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    config = AlgoConfig(
        instrument_strategy_map={"INFY": "ema_crossover"},
        algo_name="test",
    )
    reg = AlgoRegistry(config=config, session_factory=sf, repo=Repository())
    runner = AlgoRunner(reg)

    task = asyncio.get_event_loop().create_task(runner.start())
    await asyncio.sleep(0.05)

    assert runner.state == ComponentState.RUNNING
    assert "test" in runner.name

    await runner.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_algo_runner_name_includes_algo_name(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    config = AlgoConfig(
        instrument_strategy_map={"INFY": "ema_crossover"},
        algo_name="momentum",
    )
    reg = AlgoRegistry(config=config, session_factory=sf, repo=Repository())
    runner = AlgoRunner(reg)
    assert "momentum" in runner.name


# ---------------------------------------------------------------------------
# RiskController
# ---------------------------------------------------------------------------


async def test_risk_controller_starts_and_reaches_running(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    config = RiskConfig(equity=100_000.0, rc_id="default")
    circuit = CircuitBreaker()
    reg = RiskRegistry(config=config, circuit=circuit, session_factory=sf, repo=Repository())
    ctrl = RiskController(reg)

    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    assert ctrl.state == ComponentState.RUNNING

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# OrderExecutor
# ---------------------------------------------------------------------------


async def test_order_executor_starts_and_reaches_running(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)
    config = ExecConfig(exec_id="paper")
    reg = ExecRegistry(
        config=config,
        broker=_StubBroker(),
        session_factory=sf,
        repo=Repository(),
        price_store=PriceStore(),
    )
    executor = OrderExecutor(reg)

    task = asyncio.get_event_loop().create_task(executor.start())
    await asyncio.sleep(0.05)

    assert executor.state == ComponentState.RUNNING
    assert "paper" in executor.name

    await executor.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# CandleAggregator
# ---------------------------------------------------------------------------


async def test_candle_aggregator_starts_and_reaches_running(engine: AsyncEngine) -> None:
    sf = build_session_factory(engine)

    # Seed an instrument so the registry knows the token
    from trading.core.database import get_session
    async with get_session(engine) as s:
        s.add(Instrument(token=1, symbol="INFY", exchange="NSE", instrument_type="EQUITY"))

    config = CandleConfig(
        instruments=[Instrument(token=1, symbol="INFY", exchange="NSE", instrument_type="EQUITY")],
        intervals=["1min"],
        warmup_count=5,
    )
    reg = CandleRegistry(
        config=config,
        broker=_StubBroker(),
        session_factory=sf,
        repo=Repository(),
    )
    agg = CandleAggregator(reg)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.1)

    assert agg.state == ComponentState.RUNNING

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_candle_aggregator_add_algo_registry_and_warmup_replay(
    engine: AsyncEngine,
) -> None:
    """add_algo_registry registers a callback and warmup candles are replayed."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from trading.core.schemas import CandleEvent, InstrumentType

    candle = CandleEvent(
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        interval="1min",
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000,
        timestamp=datetime(2025, 1, 6, 9, 15, tzinfo=UTC),
        tick_log_id=0,
    )

    mock_candle_reg = MagicMock()
    mock_candle_reg.warmup = AsyncMock(return_value=[candle])

    mock_algo_reg = MagicMock()
    mock_algo_reg.handle = AsyncMock(return_value=[])

    agg = CandleAggregator(mock_candle_reg)
    agg.add_algo_registry(mock_algo_reg)

    await agg._setup()

    mock_algo_reg.handle.assert_called_once_with(candle)


async def test_candle_aggregator_warmup_error_does_not_abort(
    engine: AsyncEngine,
) -> None:
    """An exception in a warmup replay call is logged but does not propagate."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from trading.core.schemas import CandleEvent, InstrumentType

    candle = CandleEvent(
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        interval="1min",
        open=100.0,
        high=105.0,
        low=99.0,
        close=103.0,
        volume=1000,
        timestamp=datetime(2025, 1, 6, 9, 15, tzinfo=UTC),
        tick_log_id=0,
    )

    mock_candle_reg = MagicMock()
    mock_candle_reg.warmup = AsyncMock(return_value=[candle])

    mock_algo_reg = MagicMock()
    mock_algo_reg.handle = AsyncMock(side_effect=RuntimeError("boom"))

    agg = CandleAggregator(mock_candle_reg)
    agg.add_algo_registry(mock_algo_reg)

    # Should complete without raising
    await agg._setup()


async def test_candle_aggregator_no_warmup_candles_no_replay(
    engine: AsyncEngine,
) -> None:
    """When warmup() returns an empty list, no algo handles are called."""
    from unittest.mock import AsyncMock, MagicMock

    mock_candle_reg = MagicMock()
    mock_candle_reg.warmup = AsyncMock(return_value=[])

    mock_algo_reg = MagicMock()
    mock_algo_reg.handle = AsyncMock(return_value=[])

    agg = CandleAggregator(mock_candle_reg)
    agg.add_algo_registry(mock_algo_reg)

    await agg._setup()

    mock_algo_reg.handle.assert_not_called()
