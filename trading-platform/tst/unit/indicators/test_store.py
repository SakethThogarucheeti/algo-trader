"""Tests for indicators/store.py — CandleStore (mock-based + Postgres round-trip)."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.indicators.store import CandleStore


@pytest.mark.asyncio
async def test_fetch_since_no_redis() -> None:
    since = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    expected_rows = [{"symbol": "T", "interval": "15min", "ts": since, "close": 100.0}]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles_since = AsyncMock(return_value=expected_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo)
    result = await store.fetch_since("T", "15min", since)

    assert result == expected_rows
    mock_repo.get_candles_since.assert_called_once_with(mock_session, "T", "15min", since)


@pytest.mark.asyncio
async def test_redis_cache_hit_skips_db() -> None:
    import json

    cached_rows = [{"close": 200.0, "ts": "2024-01-01T09:15:00+00:00"}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_rows).encode())

    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_repo = MagicMock()

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 10)

    assert result == cached_rows
    mock_repo.get_candles.assert_not_called()


@pytest.mark.asyncio
async def test_redis_get_error_falls_through_to_db() -> None:
    db_rows = [{"close": 300.0}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles = AsyncMock(return_value=db_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 5)

    assert result == db_rows


@pytest.mark.asyncio
async def test_redis_setex_error_is_swallowed() -> None:
    db_rows = [{"close": 150.0}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(side_effect=ConnectionError("redis down"))

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles = AsyncMock(return_value=db_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 5)

    assert result == db_rows


# ---------------------------------------------------------------------------
# Postgres round-trip tests (require testcontainers)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def pg_engine(pg_container):
    from sqlalchemy.ext.asyncio import create_async_engine
    from trading.core.database import init_db

    url = (
        pg_container.get_connection_url()
        .replace("psycopg2", "asyncpg")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    eng = create_async_engine(url, echo=False)
    await init_db(eng)
    yield eng
    from sqlalchemy import text
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE candles CASCADE"))
    await eng.dispose()


@pytest.mark.asyncio
async def test_save_and_get_candles(pg_engine) -> None:
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    rows = [
        {"symbol": "INFY", "interval": "15min",
         "ts": datetime(2024, 1, 2, 9, 15, tzinfo=UTC),
         "open": 1500.0, "high": 1510.0, "low": 1495.0, "close": 1505.0, "volume": 10000},
        {"symbol": "INFY", "interval": "15min",
         "ts": datetime(2024, 1, 2, 9, 30, tzinfo=UTC),
         "open": 1505.0, "high": 1520.0, "low": 1500.0, "close": 1515.0, "volume": 12000},
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    async with sf() as session:
        result = await repo.get_candles(session, "INFY", "15min", limit=10)

    assert len(result) == 2
    assert result[0]["close"] == pytest.approx(1505.0)
    assert result[1]["close"] == pytest.approx(1515.0)
    assert result[0]["ts"] < result[1]["ts"]


@pytest.mark.asyncio
async def test_save_candles_idempotent(pg_engine) -> None:
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    row = {"symbol": "TCS", "interval": "1min",
           "ts": datetime(2024, 1, 3, 9, 15, tzinfo=UTC),
           "open": 3000.0, "high": 3010.0, "low": 2995.0, "close": 3005.0, "volume": 5000}

    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, [row])
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, [row])

    async with sf() as session:
        result = await repo.get_candles(session, "TCS", "1min", limit=10)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_candles_since(pg_engine) -> None:
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    base = datetime(2024, 1, 4, 9, 0, tzinfo=UTC)
    rows = [
        {"symbol": "RELIANCE", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 2000.0, "high": 2010.0, "low": 1995.0, "close": 2005.0, "volume": 8000}
        for i in range(10)
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    since = base + timedelta(minutes=15 * 5)
    async with sf() as session:
        result = await repo.get_candles_since(session, "RELIANCE", "15min", since)

    assert len(result) == 5


@pytest.mark.asyncio
async def test_candle_store_end_to_end(pg_engine) -> None:
    from trading.indicators.library.ema import EMA
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    base = datetime(2024, 1, 5, 9, 15, tzinfo=UTC)
    rows = [
        {"symbol": "HDFC", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.0, "volume": 1000}
        for i in range(30)
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    store = CandleStore(session_factory=sf, repo=repo)
    ema = EMA(store, "HDFC", "15min")
    result = await ema.compute(EMA.Parameters(period=9))
    assert result == pytest.approx(200.0, rel=1e-3)


@pytest.mark.asyncio
async def test_candle_store_redis_cache(pg_engine) -> None:
    import fakeredis.aioredis as fakeredis
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()
    redis = fakeredis.FakeRedis()

    base = datetime(2024, 1, 6, 9, 15, tzinfo=UTC)
    rows = [
        {"symbol": "WIPRO", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 300.0, "high": 301.0, "low": 299.0, "close": 300.0, "volume": 500}
        for i in range(20)
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    store = CandleStore(session_factory=sf, repo=repo, redis=redis)
    r1 = await store.fetch("WIPRO", "15min", 20)
    r2 = await store.fetch("WIPRO", "15min", 20)

    assert len(r1) == len(r2) == 20
    assert r1[0]["close"] == r2[0]["close"]
    keys = await redis.keys("cs:candles:WIPRO:15min:*")
    assert len(keys) == 1
