"""DB fetch helpers shared by all report periods."""

from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _safe_json(s: str | None) -> dict:
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        logger.warning("reports: malformed JSON: %r", s[:100])
        return {}

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trading.core.models import AlgoConfig, AuditLog, DecisionLog, Heartbeat, Signal


async def fetch_signals(session: AsyncSession, start: datetime, end: datetime) -> list[Signal]:
    result = await session.execute(
        select(Signal)
        .where(Signal.created_at >= start, Signal.created_at < end)
        .options(selectinload(Signal.orders))
        .order_by(Signal.created_at)
    )
    return list(result.scalars().all())


async def fetch_decisions(
    session: AsyncSession, start: datetime, end: datetime
) -> list[DecisionLog]:
    result = await session.execute(
        select(DecisionLog)
        .where(DecisionLog.created_at >= start, DecisionLog.created_at < end)
        .order_by(DecisionLog.created_at)
    )
    return list(result.scalars().all())


async def fetch_audit_logs(
    session: AsyncSession, start: datetime, end: datetime
) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.created_at >= start, AuditLog.created_at < end)
        .order_by(AuditLog.created_at)
    )
    return list(result.scalars().all())


async def fetch_heartbeats(session: AsyncSession) -> list[Heartbeat]:
    """Current heartbeat snapshot — not windowed by date."""
    result = await session.execute(select(Heartbeat).order_by(Heartbeat.module))
    return list(result.scalars().all())


async def fetch_algo_configs(session: AsyncSession) -> list[dict[str, object]]:
    """Current algo config + state snapshot — not windowed by date."""
    result = await session.execute(select(AlgoConfig).options(selectinload(AlgoConfig.state)))
    configs = result.scalars().all()
    out = []
    for cfg in configs:
        state = _safe_json(cfg.state.state if cfg.state else None)
        out.append({
            "name": cfg.name,
            "strategy_id": cfg.strategy_id,
            "equity": cfg.equity,
            "enabled": cfg.enabled,
            "params": _safe_json(cfg.params),
            "warmup_candles": cfg.warmup_candles,
            "state": state,
        })
    return out
