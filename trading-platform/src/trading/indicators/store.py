"""CandleStore — Postgres-backed candle data source with optional Redis caching."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.indicators.types import CandleRow
from trading.storage.stores.candle import CandleDataStore

_log = logging.getLogger(__name__)


class AbstractCandleStore(ABC):
    """Common interface for all candle data sources (Postgres-backed or in-memory)."""

    @abstractmethod
    async def fetch(self, symbol: str, interval: str, limit: int) -> list[CandleRow]:
        """Return the last *limit* candles ordered ts ASC (oldest→newest)."""

    @abstractmethod
    async def fetch_since(self, symbol: str, interval: str, since: datetime) -> list[CandleRow]:
        """Return all candles with ts >= *since*, ordered ts ASC."""


@runtime_checkable
class RedisClientProtocol(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def setex(self, key: str, ttl: int, value: str) -> None: ...

# Redis TTL for cached candle lists (seconds). One bar is typically 1–15 min,
# so 90 s ensures the cache expires well within the next bar.
_CACHE_TTL = 90


class CandleStore(AbstractCandleStore):
    """
    Fetch candle rows from Postgres for indicator computation.

    When a Redis client is supplied, raw candle lists are cached keyed by
    ``(symbol, interval, limit)`` or ``(symbol, interval, since_iso)``.
    All indicator objects that need the same window share one cache entry,
    so only one DB round-trip occurs per bar per unique fetch signature.

    Redis is purely optional — when absent all reads go directly to Postgres.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        candle_store: CandleDataStore,
        redis: RedisClientProtocol | None = None,
    ) -> None:
        self._sf = session_factory
        self._candle = candle_store
        self._redis = redis  # redis.asyncio.Redis instance or None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, symbol: str, interval: str, limit: int) -> list[CandleRow]:
        """Return the last *limit* candles ordered ts ASC (oldest→newest)."""
        cache_key = f"cs:candles:{symbol}:{interval}:n{limit}"
        return await self._get_or_fetch(
            cache_key,
            lambda: self._candle.get_candles(symbol, interval, limit),
        )

    async def fetch_since(self, symbol: str, interval: str, since: datetime) -> list[CandleRow]:
        """Return all candles with ts >= *since*, ordered ts ASC."""
        cache_key = f"cs:candles:{symbol}:{interval}:since:{since.isoformat()}"
        return await self._get_or_fetch(
            cache_key,
            lambda: self._candle.get_candles_since(symbol, interval, since),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_or_fetch(
        self,
        key: str,
        query: Callable[[], Coroutine[Any, Any, list[CandleRow]]],
    ) -> list[CandleRow]:
        if self._redis is not None:
            try:
                cached = await self._redis.get(key)
                if cached is not None:
                    # json.loads returns Any — the shape matches CandleRow at
                    # runtime but can't be verified statically without a schema validator.
                    return json.loads(cached)  # type: ignore[no-any-return]
            except Exception as exc:
                _log.debug("CandleStore: Redis get failed for %r — %s", key, exc)

        rows: list[CandleRow] = await query()

        if self._redis is not None and rows:
            try:
                await self._redis.setex(key, _CACHE_TTL, json.dumps(rows, default=str))
            except Exception as exc:
                _log.debug("CandleStore: Redis set failed for %r — %s", key, exc)

        return rows
