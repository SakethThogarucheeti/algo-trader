"""CandleStore — Postgres-backed candle data source with optional Redis caching."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.storage.base import AbstractRepository

_log = logging.getLogger(__name__)

# Redis TTL for cached candle lists (seconds). One bar is typically 1–15 min,
# so 90 s ensures the cache expires well within the next bar.
_CACHE_TTL = 90


class CandleStore:
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
        repo: AbstractRepository,
        redis: object | None = None,
    ) -> None:
        self._sf = session_factory
        self._repo = repo
        self._redis = redis  # redis.asyncio.Redis instance or None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(self, symbol: str, interval: str, limit: int) -> list[dict]:
        """Return the last *limit* candles ordered ts ASC (oldest→newest)."""
        cache_key = f"cs:candles:{symbol}:{interval}:n{limit}"
        return await self._get_or_fetch(
            cache_key,
            lambda session: self._repo.get_candles(session, symbol, interval, limit),
        )

    async def fetch_since(self, symbol: str, interval: str, since: datetime) -> list[dict]:
        """Return all candles with ts >= *since*, ordered ts ASC."""
        cache_key = f"cs:candles:{symbol}:{interval}:since:{since.isoformat()}"
        return await self._get_or_fetch(
            cache_key,
            lambda session: self._repo.get_candles_since(session, symbol, interval, since),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get_or_fetch(self, key: str, query) -> list[dict]:
        if self._redis is not None:
            try:
                cached = await self._redis.get(key)
                if cached is not None:
                    return json.loads(cached)
            except Exception as exc:
                _log.debug("CandleStore: Redis get failed for %r — %s", key, exc)

        async with self._sf() as session:
            rows = await query(session)

        if self._redis is not None and rows:
            try:
                await self._redis.setex(key, _CACHE_TTL, json.dumps(rows, default=str))
            except Exception as exc:
                _log.debug("CandleStore: Redis set failed for %r — %s", key, exc)

        return rows
