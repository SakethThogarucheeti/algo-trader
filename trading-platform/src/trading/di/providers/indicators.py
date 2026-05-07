"""DI provider for the indicator library."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.indicators.context import IndicatorContext
from trading.indicators.store import CandleStore
from trading.storage.base import AbstractRepository


def make_candle_store(
    session_factory: async_sessionmaker[AsyncSession],
    repo: AbstractRepository,
    redis: object | None = None,
) -> CandleStore:
    """Build the shared CandleStore, wiring in Redis when configured."""
    return CandleStore(session_factory=session_factory, repo=repo, redis=redis)


def make_indicator_context(store: CandleStore) -> IndicatorContext:
    """Build the IndicatorContext that binds indicators before on_candle."""
    return IndicatorContext(store=store)
