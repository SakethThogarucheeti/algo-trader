"""Tests for core/messaging.py"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest

from trading.core.messaging import MessageBus
from trading.core.schemas import InstrumentType, TickEvent

NOW = datetime.now(UTC)


def make_tick(**overrides: object) -> TickEvent:
    base = dict(
        instrument_token=1,
        instrument_type=InstrumentType.EQUITY,
        last_price=100.0,
        volume=500,
        timestamp=NOW,
        tick_log_id=1,
    )
    return TickEvent(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> MessageBus:
    return MessageBus(fake_redis)


# ---------------------------------------------------------------------------
# publish → subscribe delivery
# ---------------------------------------------------------------------------


async def test_published_message_received_by_handler(bus: MessageBus) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)  # let the listener task subscribe

    tick = make_tick(instrument_token=42, last_price=200.0)
    await bus.publish("ticks", tick)
    await asyncio.sleep(0.05)  # let the handler run

    assert len(received) == 1
    assert received[0].instrument_token == 42
    assert received[0].last_price == 200.0


async def test_handler_receives_correct_type(bus: MessageBus) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)
    await bus.publish("ticks", make_tick())
    await asyncio.sleep(0.05)

    assert isinstance(received[0], TickEvent)


async def test_multiple_subscribers_both_receive(bus: MessageBus) -> None:
    received_a: list[TickEvent] = []
    received_b: list[TickEvent] = []

    bus.subscribe("ticks", TickEvent, lambda e: received_a.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    bus.subscribe("ticks", TickEvent, lambda e: received_b.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    await asyncio.sleep(0.05)
    await bus.publish("ticks", make_tick())
    await asyncio.sleep(0.1)

    assert len(received_a) == 1
    assert len(received_b) == 1


# ---------------------------------------------------------------------------
# Bad message resilience
# ---------------------------------------------------------------------------


async def test_invalid_json_skipped_loop_continues(bus: MessageBus) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)

    # Publish raw garbage directly (not via bus.publish)
    await bus._redis.publish("ticks", b"not-json-at-all")
    # Then publish a valid message
    await bus.publish("ticks", make_tick(instrument_token=99))
    await asyncio.sleep(0.1)

    # Only the valid message should arrive
    assert len(received) == 1
    assert received[0].instrument_token == 99


async def test_invalid_schema_skipped_loop_continues(bus: MessageBus) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)

    # Valid JSON but wrong schema (last_price missing)
    await bus._redis.publish("ticks", b'{"instrument_token": 1}')
    await bus.publish("ticks", make_tick(instrument_token=77))
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].instrument_token == 77


async def test_handler_exception_does_not_kill_loop(bus: MessageBus) -> None:
    calls: list[int] = []

    async def flaky_handler(event: TickEvent) -> None:
        calls.append(event.instrument_token)
        if event.instrument_token == 1:
            raise RuntimeError("oops")

    bus.subscribe("ticks", TickEvent, flaky_handler)
    await asyncio.sleep(0.05)

    await bus.publish("ticks", make_tick(instrument_token=1))  # raises in handler
    await bus.publish("ticks", make_tick(instrument_token=2))  # should still arrive
    await asyncio.sleep(0.1)

    assert 1 in calls
    assert 2 in calls


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


async def test_set_and_get_flag(bus: MessageBus) -> None:
    await bus.set_flag("circuit:ingestor:open", "1")
    assert await bus.get_flag("circuit:ingestor:open") == "1"


async def test_get_flag_missing_returns_none(bus: MessageBus) -> None:
    assert await bus.get_flag("nonexistent") is None


async def test_set_flag_with_expiry(bus: MessageBus) -> None:
    await bus.set_flag("temp_flag", "x", ex=60)
    assert await bus.get_flag("temp_flag") == "x"


async def test_delete_flag(bus: MessageBus) -> None:
    await bus.set_flag("to_delete", "y")
    await bus.delete_flag("to_delete")
    assert await bus.get_flag("to_delete") is None


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------


async def test_close_cancels_subscription_tasks(bus: MessageBus) -> None:
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:  # pragma: no cover
        received.append(event)

    task = bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)

    await bus.close()

    assert task.cancelled() or task.done()
    assert bus._tasks == []
