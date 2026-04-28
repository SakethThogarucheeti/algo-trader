"""
Root conftest.py for strategy-testing.

Adds the strategy-testing package root to sys.path so that both the
``testing`` library and ``strategy-testing`` tests can import each other
without installing the package first.

Also provides session-scoped Postgres + Redis fixtures (via testcontainers)
for tests that run a full BacktestSession.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.core.database import init_db
from trading.core.messaging import MessageBus, RedisMessageBus

# Add strategy-testing/ to path so `import testing` resolves
sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Testcontainers — real Postgres + Redis, scope=session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    """Start a real Postgres container for the test session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    """Start a real Redis container for the test session."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.wait_strategies import LogMessageWaitStrategy

    with (
        DockerContainer("redis:7-alpine")
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections")) as r
    ):
        yield r


# ---------------------------------------------------------------------------
# Per-test fixtures derived from the containers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pg_engine(pg_container) -> AsyncEngine:
    """
    Async engine connected to the test Postgres container.

    Tables are created on first use (init_db is idempotent).
    All rows are truncated after each test so tests don't share state.
    """
    url = (
        pg_container.get_connection_url()
        .replace("psycopg2", "asyncpg")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    eng = create_async_engine(url, echo=False)
    await init_db(eng)
    yield eng
    # Truncate all application tables after each test (cascade handles FKs)
    from sqlalchemy import text

    async with eng.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE orders, signals, positions, instruments, "
                "heartbeats, audit_logs, decision_logs, tick_logs CASCADE"
            )
        )
    await eng.dispose()


@pytest_asyncio.fixture
async def redis_client(redis_container) -> Redis:
    """
    Fresh async Redis client per test.

    The container is session-scoped, but each test gets its own connection
    so that pub/sub subscriptions from a previous test don't bleed through.
    """
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client: Redis = Redis(host=host, port=int(port), decode_responses=False)
    yield client
    await client.aclose()


@pytest.fixture
def bus(redis_client) -> MessageBus:
    """MessageBus backed by the real test Redis."""
    return RedisMessageBus(redis_client)
