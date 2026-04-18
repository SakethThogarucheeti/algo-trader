"""
State recovery tests.

Verifies that:
- Duplicate orders are not placed if the process restarts mid-trade.
- Idempotency holds across multiple executions with the same signal_id.
- The repository can read back orders after a DB write.
"""

from __future__ import annotations

import uuid

import pytest

from trading.broker.paper_broker import PriceStore
from trading.core.models import Order
from trading.core.schemas import (
    InstrumentType,
    OrderType,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.executor import DirectExecutionEngine
from trading.storage.repository import Repository


def _validated_order(signal_id: uuid.UUID | None = None) -> ValidatedOrderEvent:
    return ValidatedOrderEvent(
        signal_id=signal_id or uuid.uuid4(),
        symbol="RELIANCE",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        quantity=5,
        order_type=OrderType.MARKET,
        tick_log_id=0,
    )


@pytest.mark.asyncio
async def test_no_duplicate_order_on_restart(engine, session_factory, bus):
    """
    Simulating a 'restart': execute the same signal_id twice.
    The second execution must be silently dropped (idempotency).
    """
    price_store = PriceStore()
    price_store.update("RELIANCE", 2000.0)

    repo = Repository()
    broker_calls: list[str] = []

    class _CountingBroker:
        async def place_order(self, symbol, side, qty, order_type, limit_price=None):
            order_id = f"ORDER_{uuid.uuid4().hex[:8]}"
            broker_calls.append(order_id)
            return order_id

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
    event = _validated_order(signal_id)

    await eng.execute(event)
    first_call_count = len(broker_calls)

    # "restart" — execute again with the same signal_id
    await eng.execute(event)

    assert (
        len(broker_calls) == first_call_count
    ), f"Broker was called {len(broker_calls)} times for the same signal_id; expected {first_call_count}"


@pytest.mark.asyncio
async def test_order_persisted_in_db(engine, session_factory, bus):
    """Placed orders must be readable back from the database."""
    price_store = PriceStore()
    price_store.update("RELIANCE", 2000.0)

    repo = Repository()

    class _SimpleBroker:
        async def place_order(self, *a, **kw):
            return f"ORDER_{uuid.uuid4().hex[:8]}"

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    eng = DirectExecutionEngine(
        bus=bus,
        broker=_SimpleBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=None,
    )

    event = _validated_order()
    await eng.execute(event)

    # Verify the order row exists in DB
    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(Order).where(Order.signal_id == event.signal_id))
        order_row = result.scalar_one_or_none()

    assert order_row is not None, "Order row should exist in database after execute()"
    assert order_row.qty == 5
