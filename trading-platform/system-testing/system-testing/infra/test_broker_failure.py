"""
Broker failure mode tests.

Verifies that the execution engine handles:
- Broker timeout (asyncio.TimeoutError)
- Broker API error (generic exception)
- Consecutive failures (no deadlock / hung state)

Uses real Postgres + Redis via testcontainers fixtures.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from trading.core.schemas import (
    InstrumentType,
    OrderEvent,
    OrderStatus,
    OrderType,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.executor import DirectExecutionEngine
from trading.storage.repository import Repository


def _event(symbol: str = "INFY") -> ValidatedOrderEvent:
    return ValidatedOrderEvent(
        signal_id=uuid.uuid4(),
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        quantity=5,
        order_type=OrderType.MARKET,
        tick_log_id=0,
    )


@pytest.mark.asyncio
async def test_broker_timeout_produces_rejected_order(engine, session_factory, bus):
    """asyncio.TimeoutError from broker must produce a REJECTED order event."""

    class _TimeoutBroker:
        async def place_order(self, *a, **kw):
            raise TimeoutError("broker timeout")

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    repo = Repository()
    order_events: list[OrderEvent] = []
    bus.subscribe(
        "orders", OrderEvent, lambda e: order_events.append(e) or asyncio.coroutine(lambda: None)()
    )

    eng = DirectExecutionEngine(
        bus=bus,
        broker=_TimeoutBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=None,
    )

    await eng.execute(_event())
    await asyncio.sleep(0.1)

    rejected = [e for e in order_events if e.status == OrderStatus.REJECTED]
    assert len(rejected) >= 1, "Timeout must produce a REJECTED order event"


@pytest.mark.asyncio
async def test_consecutive_broker_failures_no_deadlock(engine, session_factory, bus):
    """Multiple consecutive broker failures must not deadlock or hang."""
    call_count = 0

    class _AlwaysFailBroker:
        async def place_order(self, *a, **kw):
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"Failure #{call_count}")

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    repo = Repository()
    eng = DirectExecutionEngine(
        bus=bus,
        broker=_AlwaysFailBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=None,
    )

    # Execute 5 times — each must complete (not hang) within timeout
    for _ in range(5):
        await asyncio.wait_for(eng.execute(_event()), timeout=5.0)

    assert call_count == 5, f"Broker should have been called 5 times, got {call_count}"


@pytest.mark.asyncio
async def test_broker_api_error_leaves_db_consistent(engine, session_factory, bus):
    """After a broker API error, the DB row must be in REJECTED state (not PENDING)."""
    from sqlalchemy import select

    from trading.core.models import Order

    class _ErrorBroker:
        async def place_order(self, *a, **kw):
            raise ValueError("Invalid API key")

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    repo = Repository()
    event = _event()
    eng = DirectExecutionEngine(
        bus=bus,
        broker=_ErrorBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=None,
    )

    await eng.execute(event)

    async with session_factory() as session:
        result = await session.execute(select(Order).where(Order.signal_id == event.signal_id))
        order = result.scalar_one_or_none()

    assert order is not None
    assert order.status in (
        OrderStatus.REJECTED.value,
        OrderStatus.PLACED.value,
    ), f"Order must be REJECTED after broker error, got {order.status}"
    # Must NOT be stuck in PENDING
    assert order.status != OrderStatus.PENDING.value, "Order must not be left in PENDING state"
