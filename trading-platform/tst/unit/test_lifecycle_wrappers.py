"""Tests for thin lifecycle wrappers: AlgoRunner, RiskController, OrderExecutor"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.broker.paper_broker import PriceStore
from trading.broker.base.broker import Broker
from trading.core.database import build_session_factory, init_db
from trading.core.models import Instrument
from trading.engine.candle_aggregator import CandleAggregator
from trading.engine.algo_runner import AlgoRunner
from trading.engine.component import ComponentState
from trading.execution.executor import OrderExecutor
from trading.registry.algo import AlgoConfig, AlgoRegistry
from trading.registry.candle import CandleConfig, CandleRegistry
from trading.registry.exec import ExecConfig, ExecRegistry
from trading.registry.risk import RiskConfig, RiskRegistry
from trading.registry.tick import CircuitBreaker
from trading.risk.base import RiskController
from trading.storage.repository import Repository

import polars as pl


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
        instrument_feature_map={"INFY": "technical"},
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
        instrument_feature_map={"INFY": "technical"},
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
    from datetime import UTC, datetime, timedelta
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
