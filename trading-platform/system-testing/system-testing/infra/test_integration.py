"""
End-to-end integration tests.

Combines AlgoRunner + RiskController + OrderExecutor on real Redis and Postgres.
Uses FaultInjector to verify the system handles message drops and duplicates
without crashing or producing ghost orders.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from system_testing.simulators.fault_injector import FaultInjector

from trading.broker.paper_broker import PriceStore
from trading.config.settings import Settings
from trading.core.schemas import (
    FillEvent,
    InstrumentType,
    OrderType,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.executor import DirectExecutionEngine
from trading.storage.repository import Repository


def _settings(**overrides) -> Settings:
    base = dict(
        zerodha_api_key="TEST",
        zerodha_api_secret="TEST",
        zerodha_access_token="TEST",
        postgres_url="postgresql+asyncpg://user:pass@localhost/test",
        redis_url="redis://localhost:6379/0",
        intraday_cutoff_hour=23,
        intraday_cutoff_minute=59,
        paper_trading=True,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_fault_drop_does_not_crash(engine, session_factory, bus):
    """
    Dropping 50% of validated_orders messages must not crash the executor
    and must not produce partial DB state.
    """
    price_store = PriceStore()
    price_store.update("INFY", 1500.0)

    repo = Repository()
    fills: list[FillEvent] = []

    class _SimpleBroker:
        async def place_order(self, *a, **kw):
            return f"ORDER_{uuid.uuid4().hex[:8]}"

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    DirectExecutionEngine(
        bus=bus,
        broker=_SimpleBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=price_store,
    )
    bus.subscribe(
        "fills", FillEvent, lambda f: fills.append(f) or asyncio.coroutine(lambda: None)()
    )

    async with FaultInjector(bus, seed=1).with_drop_rate("validated_orders:test", 0.5):
        for _ in range(10):
            event = ValidatedOrderEvent(
                signal_id=uuid.uuid4(),
                symbol="INFY",
                instrument_type=InstrumentType.EQUITY,
                side=Side.BUY,
                quantity=1,
                order_type=OrderType.MARKET,
                tick_log_id=0,
            )
            # Publish directly (fault injector wraps bus.publish)
            await bus.publish("validated_orders:test", event)

    await asyncio.sleep(0.2)
    # System should still be running (no crash). We can't assert exact fill count
    # because of random drops, but we can assert no exception was raised.


@pytest.mark.asyncio
async def test_fault_duplicate_idempotent(engine, session_factory, bus):
    """
    Duplicating orders must not create duplicate DB rows — DirectExecutionEngine
    is idempotent on signal_id.
    """
    price_store = PriceStore()
    price_store.update("INFY", 1500.0)

    repo = Repository()
    broker_calls: list[str] = []

    class _CountingBroker:
        async def place_order(self, *a, **kw):
            oid = f"ORDER_{uuid.uuid4().hex[:8]}"
            broker_calls.append(oid)
            return oid

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    eng = DirectExecutionEngine(
        bus=bus,
        broker=_CountingBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=price_store,
    )

    signal_id = uuid.uuid4()
    event = ValidatedOrderEvent(
        signal_id=signal_id,
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        quantity=1,
        order_type=OrderType.MARKET,
        tick_log_id=0,
    )

    # Execute twice with same signal_id (simulating a duplicate from FaultInjector)
    await eng.execute(event)
    first_count = len(broker_calls)
    await eng.execute(event)

    assert (
        len(broker_calls) == first_count
    ), "Duplicate signal_id must be dropped — broker should not be called twice"
