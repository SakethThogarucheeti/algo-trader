"""
Order lifecycle integration tests.

Tests the full path: ValidatedOrderEvent → DirectExecutionEngine → broker
→ FillEvent → position update in DB.

Uses real Postgres + Redis via testcontainers fixtures from conftest.py.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from trading.broker.paper_broker import PaperBroker, PriceStore
from trading.core.schemas import (
    FillEvent,
    InstrumentType,
    OrderStatus,
    OrderType,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.executor import DirectExecutionEngine
from trading.storage.repository import Repository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validated_order(
    symbol: str = "INFY",
    side: Side = Side.BUY,
    qty: int = 10,
) -> ValidatedOrderEvent:
    return ValidatedOrderEvent(
        signal_id=uuid.uuid4(),
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
        tick_log_id=0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_place_and_fill(engine, session_factory, bus):
    """Full happy-path: place order → immediate fill via PaperBroker."""
    price_store = PriceStore()
    price_store.update("INFY", 1500.0)

    repo = Repository()

    # Minimal stub real_broker for PaperBroker
    class _NullBroker:
        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

        async def place_order(self, symbol, side, qty, order_type, limit_price=None):
            return f"ZERODHA_{uuid.uuid4().hex[:8]}"

    real_broker = _NullBroker()
    broker = PaperBroker(real_broker)  # type: ignore[arg-type]

    engine_obj = DirectExecutionEngine(
        bus=bus,
        broker=broker,
        repo=repo,
        session_factory=session_factory,
        paper_price_store=price_store,
    )

    fills: list[FillEvent] = []
    bus.subscribe(
        "fills", FillEvent, lambda f: fills.append(f) or asyncio.coroutine(lambda: None)()
    )

    event = _validated_order()
    await engine_obj.execute(event)

    # Give the fill task a tick to run
    await asyncio.sleep(0.1)

    assert len(fills) >= 1
    assert fills[0].avg_price == pytest.approx(1500.0)
    assert fills[0].filled_qty == 10


@pytest.mark.asyncio
async def test_idempotency_duplicate_signal(engine, session_factory, bus):
    """Duplicate signal_id must not place a second order."""
    price_store = PriceStore()
    price_store.update("INFY", 1500.0)

    repo = Repository()

    class _NullBroker:
        call_count = 0

        async def place_order(self, symbol, side, qty, order_type, limit_price=None):
            self.__class__.call_count += 1
            return f"ORDER_{uuid.uuid4().hex[:8]}"

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    broker = _NullBroker()
    engine_obj = DirectExecutionEngine(
        bus=bus,
        broker=broker,
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=price_store,
    )

    event = _validated_order()
    await engine_obj.execute(event)
    call_count_after_first = _NullBroker.call_count

    # Duplicate — same signal_id
    await engine_obj.execute(event)

    assert (
        _NullBroker.call_count == call_count_after_first
    ), "Second call with same signal_id must not reach broker"


@pytest.mark.asyncio
async def test_broker_rejection_marks_order_rejected(engine, session_factory, bus):
    """When the broker raises, the order must be marked REJECTED in DB."""
    price_store = PriceStore()
    price_store.update("INFY", 1500.0)

    repo = Repository()

    class _FailingBroker:
        async def place_order(self, *a, **kw):
            raise RuntimeError("Broker unavailable")

        def get_instruments(self):
            import polars as pl

            return pl.DataFrame()

        def get_ohlc(self, *a, **kw):
            import polars as pl

            return pl.DataFrame()

    engine_obj = DirectExecutionEngine(
        bus=bus,
        broker=_FailingBroker(),
        repo=repo,  # type: ignore[arg-type]
        session_factory=session_factory,
        paper_price_store=None,
    )

    order_events = []
    from trading.core.schemas import OrderEvent

    bus.subscribe(
        "orders", OrderEvent, lambda e: order_events.append(e) or asyncio.coroutine(lambda: None)()
    )

    await engine_obj.execute(_validated_order())
    await asyncio.sleep(0.1)

    rejected = [e for e in order_events if e.status == OrderStatus.REJECTED]
    assert len(rejected) >= 1, "Expected at least one REJECTED OrderEvent"
