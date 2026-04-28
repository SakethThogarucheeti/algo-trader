from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from trading.broker.paper_broker import AbstractPriceStore, PriceStore
from trading.config.settings import Settings, get_settings
from trading.core.database import build_engine, build_session_factory
from trading.storage.base import AbstractRepository
from trading.storage.repository import Repository


class InfrastructureProvider(Provider):
    """
    Singletons that live for the entire process lifetime.

    Provides: Settings, AsyncEngine, async_sessionmaker, Repository, PriceStore.
    Redis and MessageBus have been removed — inter-component communication
    now happens via direct registry calls in pipeline.py.
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
    def repository(self) -> AbstractRepository:
        return Repository()

    @provide
    def price_store(self) -> AbstractPriceStore:
        return PriceStore()
