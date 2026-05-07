"""Core report runner — fetch data for a window, then render."""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from trading.reports.fetch import (
    fetch_algo_configs,
    fetch_audit_logs,
    fetch_decisions,
    fetch_heartbeats,
    fetch_signals,
)
from trading.reports.render import hr, print_strategy_section, print_system_section


def _find_db_url() -> str:
    from pathlib import Path

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            break

    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL", "")
    if not url:
        sys.exit("ERROR: DATABASE_URL or POSTGRES_URL must be set in .env")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def run_report(start: datetime, end: datetime, title: str) -> None:
    """Fetch all data for [start, end) and print the full report."""
    engine = create_async_engine(_find_db_url(), echo=False)

    async with AsyncSession(engine) as session:
        signals = await fetch_signals(session, start, end)
        decisions = await fetch_decisions(session, start, end)
        audit_logs = await fetch_audit_logs(session, start, end)
        heartbeats = await fetch_heartbeats(session)
        algo_configs = await fetch_algo_configs(session)

    await engine.dispose()

    print()
    hr("═")
    print(f"  {title}")
    hr("═")
    print(f"  Period:    {start.strftime('%Y-%m-%d %H:%M')} – {end.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")

    print_strategy_section(signals, decisions, algo_configs)
    print_system_section(decisions, audit_logs, heartbeats)

    print()
    hr("═")
    print("  END OF REPORT")
    hr("═")
    print()
