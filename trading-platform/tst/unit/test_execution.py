"""Tests for execution/idempotency.py and execution/executor.py"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.broker.base.broker import Broker
from trading.core.database import build_session_factory, get_session, init_db
from trading.core.messaging import MessageBus
from trading.core.models import Order, Signal
from trading.core.schemas import (
    FillEvent,
    InstrumentType,
    OrderEvent,
    OrderStatus,
    OrderType,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.executor import DirectExecutionEngine, OrderExecutor
from trading.execution.idempotency import is_duplicate
from trading.storage.repository import Repository

NOW = datetime.now(UTC)

# ---------------------------------------------------------------------------
# Mock broker
# ---------------------------------------------------------------------------


class MockBroker(Broker):
    def __init__(self, order_id: str = "KITE_001", raises: bool = False) -> None:
        self._order_id = order_id
        self._raises = raises
        self.place_order_calls: list[dict] = []

    def get_instruments(self):  # type: ignore[override]
        import polars as pl

        return pl.DataFrame()

    def get_ohlc(self, symbol, interval, start, end):  # type: ignore[override]
        import polars as pl

        return pl.DataFrame()

    async def place_order(self, symbol, side, qty, order_type, limit_price=None) -> str:  # type: ignore[override]
        self.place_order_calls.append(dict(symbol=symbol, side=side, qty=qty))
        if self._raises:
            raise RuntimeError("broker error")
        return self._order_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> MessageBus:
    return MessageBus(fake_redis)


def make_executor(
    engine: AsyncEngine,
    bus: MessageBus,
    broker: MockBroker | None = None,
) -> OrderExecutor:
    sf = build_session_factory(engine)
    engine_ = DirectExecutionEngine(bus, broker or MockBroker(), Repository(), sf)
    return OrderExecutor(bus, engine_)


def make_validated(signal_id=None, **overrides) -> ValidatedOrderEvent:
    base = dict(
        signal_id=signal_id or uuid4(),
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        limit_price=None,
        tick_log_id=1,
    )
    return ValidatedOrderEvent(**{**base, **overrides})  # type: ignore[arg-type]


async def _insert_signal(engine: AsyncEngine, sig_id) -> None:
    async with get_session(engine) as s:
        s.add(
            Signal(
                id=sig_id,
                strategy_id="s",
                symbol="INFY",
                instrument_type="EQUITY",
                side="BUY",
                signal_type="ENTRY",
                stop_distance=Decimal("10"),
                created_at=NOW,
            )
        )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


async def test_is_duplicate_returns_false_for_new_signal(engine: AsyncEngine) -> None:
    sig_id = uuid4()
    await _insert_signal(engine, sig_id)
    async with get_session(engine) as s:
        result = await is_duplicate(sig_id, s)
    assert result is False


async def test_is_duplicate_returns_true_when_order_exists(engine: AsyncEngine) -> None:
    sig_id = uuid4()
    await _insert_signal(engine, sig_id)
    async with get_session(engine) as s:
        s.add(
            Order(
                id=uuid4(),
                kite_order_id="K99",
                signal_id=sig_id,
                status=OrderStatus.PLACED.value,
                qty=5,
                avg_price=Decimal("0"),
                created_at=NOW,
            )
        )
    async with get_session(engine) as s:
        result = await is_duplicate(sig_id, s)
    assert result is True


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------


async def test_valid_order_publishes_order_event(engine: AsyncEngine, bus: MessageBus) -> None:
    received: list[OrderEvent] = []
    bus.subscribe("orders", OrderEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    broker = MockBroker(order_id="KITE_100")
    exec_ = make_executor(engine, bus, broker)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    sig_id = uuid4()
    await bus.publish("validated_orders", make_validated(signal_id=sig_id))
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].kite_order_id == "KITE_100"
    assert received[0].status == OrderStatus.PLACED

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_duplicate_signal_id_not_re_placed(engine: AsyncEngine, bus: MessageBus) -> None:
    broker = MockBroker()
    exec_ = make_executor(engine, bus, broker)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    sig_id = uuid4()
    event = make_validated(signal_id=sig_id)
    await bus.publish("validated_orders", event)
    await asyncio.sleep(0.15)
    # Send same signal_id again
    await bus.publish("validated_orders", event)
    await asyncio.sleep(0.15)

    # broker.place_order called only once
    assert len(broker.place_order_calls) == 1

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_broker_error_marks_order_rejected(engine: AsyncEngine, bus: MessageBus) -> None:
    received: list[OrderEvent] = []
    bus.subscribe("orders", OrderEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    broker = MockBroker(raises=True)
    exec_ = make_executor(engine, bus, broker)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    await bus.publish("validated_orders", make_validated())
    await asyncio.sleep(0.15)

    assert len(received) == 1
    assert received[0].status == OrderStatus.REJECTED

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Fill handling
# ---------------------------------------------------------------------------


async def test_fill_updates_order_status_to_filled(engine: AsyncEngine, bus: MessageBus) -> None:
    exec_ = make_executor(engine, bus)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    # Place order first
    await bus.publish("validated_orders", make_validated())
    await asyncio.sleep(0.15)

    # Find the kite_order_id from DB
    async with get_session(engine) as s:
        from sqlalchemy import select

        result = await s.execute(select(Order))
        order = result.scalars().first()
    assert order is not None
    kite_id = order.kite_order_id

    # Handle fill
    await exec_.handle_fill(
        kite_order_id=kite_id,
        avg_price=1500.0,
        filled_qty=10,
        symbol="INFY",
        instrument_type="EQUITY",
        side="BUY",
    )

    async with get_session(engine) as s:
        filled = await Repository().get_order_by_kite_id(s, kite_id)
    assert filled is not None
    assert filled.status == OrderStatus.FILLED.value
    assert float(filled.avg_price) == pytest.approx(1500.0)

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_fill_updates_position(engine: AsyncEngine, bus: MessageBus) -> None:
    exec_ = make_executor(engine, bus)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    await bus.publish("validated_orders", make_validated())
    await asyncio.sleep(0.15)

    async with get_session(engine) as s:
        from sqlalchemy import select

        result = await s.execute(select(Order))
        order = result.scalars().first()
    assert order is not None

    await exec_.handle_fill(
        kite_order_id=order.kite_order_id,
        avg_price=1500.0,
        filled_qty=10,
        symbol="INFY",
        instrument_type="EQUITY",
        side="BUY",
    )

    async with get_session(engine) as s:
        pos = await Repository().get_position(s, "INFY", "EQUITY")
    assert pos is not None
    assert pos.net_qty == 10
    assert float(pos.avg_price) == pytest.approx(1500.0)

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_broker_timeout_marks_order_rejected(engine: AsyncEngine, bus: MessageBus) -> None:
    """A broker that raises RuntimeError (the timeout wrapper's output) must mark the order REJECTED."""
    received: list[OrderEvent] = []
    bus.subscribe("orders", OrderEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    class _TimeoutBroker(MockBroker):
        async def place_order(self, symbol, side, qty, order_type, limit_price=None) -> str:  # type: ignore[override]
            raise RuntimeError("ZerodhaBroker: place_order timed out after 10.0s")

    exec_ = make_executor(engine, bus, broker=_TimeoutBroker())
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    await bus.publish("validated_orders", make_validated())
    await asyncio.sleep(0.15)

    assert len(received) == 1
    assert received[0].status == OrderStatus.REJECTED

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_stale_fill_for_unknown_order_is_skipped(
    engine: AsyncEngine, bus: MessageBus
) -> None:
    """A fill for a kite_order_id not in the DB must be silently dropped (no exception, no position update)."""
    exec_ = make_executor(engine, bus)

    # Call handle_fill with a kite_order_id that was never persisted
    await exec_.handle_fill(
        kite_order_id="GHOST_ORDER_999",
        avg_price=1500.0,
        filled_qty=10,
        symbol="INFY",
        instrument_type="EQUITY",
        side="BUY",
    )

    # Position table must remain empty — no corruption from a stale fill
    async with get_session(engine) as s:
        pos = await Repository().get_position(s, "INFY", "EQUITY")
    assert pos is None, "Stale fill must not create a position row"


async def test_stale_fill_does_not_publish_fill_event(engine: AsyncEngine, bus: MessageBus) -> None:
    """A fill for an unknown order must not publish a FillEvent downstream."""
    fills: list[FillEvent] = []
    bus.subscribe("fills", FillEvent, lambda e: fills.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    exec_ = make_executor(engine, bus)
    await exec_.handle_fill(
        kite_order_id="GHOST_ORDER_000",
        avg_price=1500.0,
        filled_qty=10,
        symbol="INFY",
        instrument_type="EQUITY",
        side="BUY",
    )
    await asyncio.sleep(0.05)

    assert len(fills) == 0, "Stale fill must not emit a FillEvent"


async def test_fill_publishes_fill_event(engine: AsyncEngine, bus: MessageBus) -> None:
    fills: list[FillEvent] = []
    bus.subscribe("fills", FillEvent, lambda e: fills.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    exec_ = make_executor(engine, bus)
    task = asyncio.get_event_loop().create_task(exec_.start())
    await asyncio.sleep(0.05)

    await bus.publish("validated_orders", make_validated())
    await asyncio.sleep(0.15)

    async with get_session(engine) as s:
        from sqlalchemy import select

        result = await s.execute(select(Order))
        order = result.scalars().first()
    assert order is not None

    await exec_.handle_fill(
        kite_order_id=order.kite_order_id,
        avg_price=1500.0,
        filled_qty=10,
        symbol="INFY",
        instrument_type="EQUITY",
        side="BUY",
    )
    await asyncio.sleep(0.05)

    assert len(fills) == 1
    assert fills[0].avg_price == pytest.approx(1500.0)

    await exec_.stop()
    await asyncio.gather(task, return_exceptions=True)
