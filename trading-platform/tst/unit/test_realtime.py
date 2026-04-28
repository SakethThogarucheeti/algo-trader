"""Tests for data/realtime.py — KiteIngestor"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus, RedisMessageBus
from trading.core.models import Instrument
from trading.core.schemas import InstrumentType, TickEvent
from trading.data.realtime import KiteIngestor
from trading.storage.repository import Repository

NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Mock broker stream
# ---------------------------------------------------------------------------


class MockBrokerStream:
    """Test double for BrokerStream. Fires callbacks programmatically."""

    def __init__(self) -> None:
        self._on_connect: Callable[[], None] | None = None
        self._on_ticks: Callable[[list[dict]], None] | None = None
        self._on_disconnect: Callable[[int, str], None] | None = None
        self.subscribed_tokens: list[int] = []
        self.closed = False

    def set_on_connect(self, callback: Callable[[], None]) -> None:
        self._on_connect = callback

    def set_on_ticks(self, callback: Callable[[list[dict]], None]) -> None:
        self._on_ticks = callback

    def set_on_disconnect(self, callback: Callable[[int, str], None]) -> None:
        self._on_disconnect = callback

    async def connect(self) -> None:
        """Immediately fires on_connect so _setup() unblocks."""
        if self._on_connect:
            self._on_connect()

    async def subscribe(self, tokens: list[int]) -> None:
        self.subscribed_tokens = list(tokens)

    async def close(self) -> None:
        self.closed = True

    # Test helpers — call from the async test to simulate broker events
    def fire_ticks(self, ticks: list[dict]) -> None:
        if self._on_ticks:
            self._on_ticks(ticks)

    def fire_disconnect(self, code: int = 1006, reason: str = "connection closed") -> None:
        if self._on_disconnect:
            self._on_disconnect(code, reason)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_instruments(*tokens: int, itype: str = "EQUITY") -> list[Instrument]:
    return [
        Instrument(token=t, symbol=f"SYM{t}", exchange="NSE", instrument_type=itype) for t in tokens
    ]


def make_raw_tick(token: int, price: float = 100.0, volume: int = 1000) -> dict:
    return {
        "instrument_token": token,
        "last_price": price,
        "volume_traded": volume,
    }


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> MessageBus:
    return RedisMessageBus(fake_redis)


@pytest.fixture
def stream() -> MockBrokerStream:
    return MockBrokerStream()


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def ingestor(stream: MockBrokerStream, bus: MessageBus, engine: AsyncEngine) -> KiteIngestor:
    instruments = make_instruments(1, 2)
    sf = build_session_factory(engine)
    return KiteIngestor(
        stream, bus, instruments, session_factory=sf, repo=Repository(), circuit_timeout_secs=0.1
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


async def test_setup_subscribes_to_tokens(
    stream: MockBrokerStream, bus: MessageBus, engine: AsyncEngine
) -> None:
    instruments = make_instruments(10, 20, 30)
    sf = build_session_factory(engine)
    ingestor = KiteIngestor(stream, bus, instruments, session_factory=sf, repo=Repository())

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    assert set(stream.subscribed_tokens) == {10, 20, 30}

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Tick publishing
# ---------------------------------------------------------------------------


async def test_valid_tick_published_to_channel(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("tick:1", TickEvent, handler)

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_ticks([make_raw_tick(token=1, price=250.0)])
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].instrument_token == 1
    assert received[0].last_price == 250.0

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_tick_with_zero_price_not_published(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    received: list[TickEvent] = []
    bus.subscribe("tick:1", TickEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_ticks([make_raw_tick(token=1, price=0.0)])  # last_price=0 → ValidationError
    await asyncio.sleep(0.05)

    assert len(received) == 0

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_tick_missing_last_price_not_published(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    received: list[TickEvent] = []
    bus.subscribe("tick:1", TickEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    # Send a tick dict with no last_price — defaults to 0 → ValidationError
    stream.fire_ticks([{"instrument_token": 1}])
    await asyncio.sleep(0.05)

    assert len(received) == 0

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_unknown_token_not_published(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    """Tick for a token not in the instruments list is silently skipped."""
    received: list[TickEvent] = []
    bus.subscribe("tick:999", TickEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_ticks([make_raw_tick(token=999, price=100.0)])
    await asyncio.sleep(0.05)

    assert len(received) == 0

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_multiple_tokens_each_to_own_channel(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    received_1: list[TickEvent] = []
    received_2: list[TickEvent] = []

    bus.subscribe("tick:1", TickEvent, lambda e: received_1.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    bus.subscribe("tick:2", TickEvent, lambda e: received_2.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_ticks(
        [
            make_raw_tick(token=1, price=100.0),
            make_raw_tick(token=2, price=200.0),
        ]
    )
    await asyncio.sleep(0.1)

    assert len(received_1) == 1
    assert received_1[0].last_price == 100.0
    assert len(received_2) == 1
    assert received_2[0].last_price == 200.0

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_instrument_type_correct_on_published_tick(
    stream: MockBrokerStream, bus: MessageBus, engine: AsyncEngine
) -> None:
    instruments = [Instrument(token=5, symbol="INFY", exchange="NSE", instrument_type="EQUITY")]
    sf = build_session_factory(engine)
    ingestor = KiteIngestor(stream, bus, instruments, session_factory=sf, repo=Repository())
    received: list[TickEvent] = []
    bus.subscribe("tick:5", TickEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_ticks([make_raw_tick(token=5, price=1500.0)])
    await asyncio.sleep(0.05)

    assert received[0].instrument_type == InstrumentType.EQUITY

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


async def test_disconnect_sets_circuit_flag_after_timeout(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    """circuit_timeout_secs=0.1 → flag set ~0.1s after disconnect."""
    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_disconnect()
    await asyncio.sleep(0.2)  # wait past the 0.1s timeout

    flag = await bus.get_flag("circuit:ingestor:open")
    assert flag == "1"

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_reconnect_before_timeout_clears_circuit_flag(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    """Reconnect before the circuit timeout cancels the flag-setting task."""
    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    stream.fire_disconnect()
    await asyncio.sleep(0.01)  # well before 0.1s timeout

    # Simulate reconnect
    stream._on_connect and stream._on_connect()  # type: ignore[misc]
    await asyncio.sleep(0.2)  # wait past the original timeout

    flag = await bus.get_flag("circuit:ingestor:open")
    assert flag is None  # reconnected → flag never set

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


async def test_stop_closes_stream(
    stream: MockBrokerStream, bus: MessageBus, ingestor: KiteIngestor
) -> None:
    task = asyncio.get_event_loop().create_task(ingestor.start())
    await asyncio.sleep(0.05)

    await ingestor.stop()
    await asyncio.gather(task, return_exceptions=True)

    assert stream.closed
