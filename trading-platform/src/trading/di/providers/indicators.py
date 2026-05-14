"""DI provider for the indicator library."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.indicators.context import IndicatorContext
from trading.indicators.store import CandleStore
from trading.storage.stores.candle import CandleDataStore


def make_candle_store(
    session_factory: async_sessionmaker[AsyncSession],
    candle_store: CandleDataStore,
    redis: object | None = None,
) -> CandleStore:
    """Build the shared CandleStore, wiring in Redis when configured."""
    return CandleStore(session_factory=session_factory, candle_store=candle_store, redis=redis)


def make_indicator_context(store: CandleStore) -> IndicatorContext:
    """Build the IndicatorContext that binds indicators before on_candle."""
    return IndicatorContext(store=store)
