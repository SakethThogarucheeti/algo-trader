"""Tests for di/providers.py and di/container.py"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC

import fakeredis.aioredis
import pytest
from dishka import AsyncContainer, Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trading.config.settings import Settings
from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus
from trading.di.container import build_container
from trading.storage.repository import Repository

# ---------------------------------------------------------------------------
# Test infrastructure provider — replaces prod InfraProvider in tests
# ---------------------------------------------------------------------------


class FakeInfraProvider(Provider):
    """Swaps prod infra (Postgres + Redis) for in-memory equivalents."""

    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return Settings(
            zerodha_api_key="test-key",
            zerodha_api_secret="test-secret",
            postgres_url="postgresql+asyncpg://u:p@localhost/test",  # not used
            redis_url="redis://localhost",  # not used
        )

    @provide
    async def db_engine(self) -> AsyncIterator[AsyncEngine]:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        await init_db(engine)
        yield engine
        await engine.dispose()

    @provide
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return build_session_factory(engine)

    @provide
    def redis_client(self) -> Redis:  # type: ignore[type-arg]
        return fakeredis.aioredis.FakeRedis()  # type: ignore[return-value]

    @provide
    def message_bus(self, redis: Redis) -> MessageBus:  # type: ignore[type-arg]
        return MessageBus(redis)

    @provide
    def repository(self) -> Repository:
        return Repository()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def container() -> AsyncIterator[AsyncContainer]:  # type: ignore[misc]
    async with build_container(FakeInfraProvider()) as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_container_resolves_settings(container: AsyncContainer) -> None:
    settings = await container.get(Settings)
    assert settings.zerodha_api_key == "test-key"


async def test_container_resolves_message_bus(container: AsyncContainer) -> None:
    bus = await container.get(MessageBus)
    assert isinstance(bus, MessageBus)


async def test_container_resolves_repository(container: AsyncContainer) -> None:
    repo = await container.get(Repository)
    assert isinstance(repo, Repository)


async def test_container_resolves_db_engine(container: AsyncContainer) -> None:
    engine = await container.get(AsyncEngine)
    assert engine is not None


async def test_container_resolves_session_factory(container: AsyncContainer) -> None:
    # async_sessionmaker is generic — retrieve via AsyncSession to confirm it works
    factory = await container.get(async_sessionmaker[AsyncSession])
    assert callable(factory)


async def test_message_bus_singleton(container: AsyncContainer) -> None:
    """Two calls to container.get(MessageBus) return the same instance."""
    bus1 = await container.get(MessageBus)
    bus2 = await container.get(MessageBus)
    assert bus1 is bus2


async def test_repository_singleton(container: AsyncContainer) -> None:
    repo1 = await container.get(Repository)
    repo2 = await container.get(Repository)
    assert repo1 is repo2


async def test_extra_provider_overrides_default(container: AsyncContainer) -> None:
    """TestInfraProvider's settings override InfrastructureProvider's settings."""
    settings = await container.get(Settings)
    # InfrastructureProvider would call get_settings() which reads the real .env;
    # TestInfraProvider returns hardcoded values — verify override worked.
    assert settings.zerodha_api_key == "test-key"


async def test_message_bus_functional_via_container(container: AsyncContainer) -> None:
    """End-to-end: publish and receive a message using the container-resolved bus."""
    import asyncio
    from datetime import datetime

    from trading.core.schemas import InstrumentType, TickEvent

    bus = await container.get(MessageBus)
    received: list[TickEvent] = []

    async def handler(event: TickEvent) -> None:
        received.append(event)

    bus.subscribe("ticks", TickEvent, handler)
    await asyncio.sleep(0.05)

    tick = TickEvent(
        instrument_token=1,
        instrument_type=InstrumentType.EQUITY,
        last_price=100.0,
        volume=500,
        timestamp=datetime.now(UTC),
        tick_log_id=1,
    )
    await bus.publish("ticks", tick)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].instrument_token == 1
