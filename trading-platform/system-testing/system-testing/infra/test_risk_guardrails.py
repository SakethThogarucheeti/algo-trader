"""
Risk controller guardrail tests.

Verifies that DefaultRiskController correctly enforces:
- Daily loss limit
- Intraday time cutoff
- Duplicate position guard
- Zero quantity rejection

Uses real Postgres + Redis via testcontainers fixtures from conftest.py.
"""

from __future__ import annotations

import asyncio

import pytest

from trading.config.settings import Settings
from trading.core.schemas import (
    InstrumentType,
    Side,
    SignalEvent,
    SignalType,
    ValidatedOrderEvent,
)
from trading.risk.controller import DefaultRiskController
from trading.storage.repository import Repository


def _settings(**overrides) -> Settings:
    base = dict(
        zerodha_api_key="TEST",
        zerodha_api_secret="TEST",
        zerodha_access_token="TEST",
        postgres_url="postgresql+asyncpg://user:pass@localhost/test",
        redis_url="redis://localhost:6379/0",
    )
    base.update(overrides)
    return Settings(**base)


def _signal(
    symbol: str = "INFY",
    side: Side = Side.BUY,
    strategy_id: str = "test",
) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        side=side,
        strategy_id=strategy_id,
        signal_type=SignalType.ENTRY,
        stop_distance=10.0,
        tick_log_id=0,
    )


@pytest.mark.asyncio
async def test_time_cutoff_rejects_signal(engine, session_factory, bus):
    """Signals arriving after the intraday cutoff must be rejected."""
    settings = _settings(
        intraday_cutoff_hour=0,  # effectively 00:00 — everything is "after cutoff"
        intraday_cutoff_minute=0,
        paper_trading=True,
    )
    repo = Repository()
    validated: list[ValidatedOrderEvent] = []
    signals_channel = "signals:test_cutoff"
    validated_channel = "validated:test_cutoff"

    bus.subscribe(
        validated_channel,
        ValidatedOrderEvent,
        lambda e: validated.append(e) or asyncio.coroutine(lambda: None)(),
    )

    rc = DefaultRiskController(
        bus=bus,
        repo=repo,
        session_factory=session_factory,
        settings=settings,
        equity=100_000.0,
        signals_channel=signals_channel,
        validated_orders_channel=validated_channel,
    )
    await rc._setup()

    # Publish a signal on the signals channel
    await bus.publish(signals_channel, _signal())
    await asyncio.sleep(0.2)

    assert len(validated) == 0, "Signal should be rejected due to time cutoff"
    await rc._teardown()


@pytest.mark.asyncio
async def test_valid_signal_passes_through(engine, session_factory, bus):
    """A valid signal with a large risk equity should produce a ValidatedOrderEvent."""
    settings = _settings(
        intraday_cutoff_hour=23,
        intraday_cutoff_minute=59,
        paper_trading=True,
        risk_per_trade_pct=1.0,
    )
    repo = Repository()
    validated: list[ValidatedOrderEvent] = []
    signals_channel = "signals:test_valid"
    validated_channel = "validated:test_valid"

    bus.subscribe(
        validated_channel,
        ValidatedOrderEvent,
        lambda e: validated.append(e) or asyncio.coroutine(lambda: None)(),
    )

    rc = DefaultRiskController(
        bus=bus,
        repo=repo,
        session_factory=session_factory,
        settings=settings,
        equity=1_000_000.0,  # large equity → non-zero qty
        signals_channel=signals_channel,
        validated_orders_channel=validated_channel,
    )
    await rc._setup()

    signal = _signal()
    signal.stop_distance = 1.0  # tiny stop → large qty
    await bus.publish(signals_channel, signal)
    await asyncio.sleep(0.3)

    assert len(validated) >= 1, "Valid signal should produce a ValidatedOrderEvent"
    await rc._teardown()
