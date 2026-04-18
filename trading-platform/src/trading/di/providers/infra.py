from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trading.broker.paper_broker import PriceStore
from trading.config.settings import Settings, get_settings
from trading.core.database import build_engine, build_session_factory
from trading.core.messaging import MessageBus
from trading.storage.repository import Repository


class InfrastructureProvider(Provider):
    """
    Singletons that live for the entire process lifetime.

    Provides: Settings, AsyncEngine, async_sessionmaker, Redis, MessageBus,
    Repository, PriceStore.
    """

    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return get_settings()

    @provide
    async def db_engine(self, settings: Settings) -> AsyncIterator[AsyncEngine]:
        engine = build_engine(str(settings.postgres_url))
        yield engine
        await engine.dispose()

    @provide
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return build_session_factory(engine)

    @provide
    async def redis_client(self, settings: Settings) -> AsyncIterator[Redis]:  # type: ignore[type-arg]
        client: Redis = Redis.from_url(str(settings.redis_url))  # type: ignore[type-arg]
        yield client
        await client.aclose()

    @provide
    def message_bus(self, redis: Redis) -> MessageBus:  # type: ignore[type-arg]
        return MessageBus(redis)

    @provide
    def repository(self) -> Repository:
        return Repository()

    @provide
    def price_store(self) -> PriceStore:
        return PriceStore()
