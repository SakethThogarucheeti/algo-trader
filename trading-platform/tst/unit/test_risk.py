"""Tests for risk/sizer.py and risk/controller.py"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.config.settings import Settings
from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus, RedisMessageBus
from trading.core.models import Order, Position, Signal
from trading.core.schemas import (
    InstrumentType,
    OrderStatus,
    Side,
    SignalEvent,
    SignalType,
    ValidatedOrderEvent,
)
from trading.risk.base import RiskController
from trading.risk.controller import DefaultRiskController
from trading.risk.sizer import calculate_quantity
from trading.storage.repository import Repository

NOW = datetime.now(UTC)
TODAY = NOW.date()

# ---------------------------------------------------------------------------
# Sizer tests
# ---------------------------------------------------------------------------


def test_sizer_basic_quantity() -> None:
    # equity=100_000, risk=1%, stop=50 → 100_000 * 0.01 / 50 = 20
    assert calculate_quantity(stop_distance=50, equity=100_000, risk_pct=1.0) == 20


def test_sizer_rounds_down_fractional() -> None:
    # 100_000 * 0.01 / 60 = 16.6... → floor → 16
    assert calculate_quantity(stop_distance=60, equity=100_000, risk_pct=1.0) == 16


def test_sizer_lot_size_rounds_down_to_lot() -> None:
    # raw=37, lot=25 → 37 // 25 * 25 = 25
    qty = calculate_quantity(stop_distance=27, equity=100_000, risk_pct=1.0, lot_size=25)
    assert qty == 25


def test_sizer_lot_size_below_one_lot_returns_zero() -> None:
    # raw=12, lot=25 → 0
    qty = calculate_quantity(stop_distance=84, equity=100_000, risk_pct=1.0, lot_size=25)
    assert qty == 0


def test_sizer_zero_stop_distance_returns_zero() -> None:
    assert calculate_quantity(stop_distance=0, equity=100_000, risk_pct=1.0) == 0


def test_sizer_negative_stop_distance_returns_zero() -> None:
    assert calculate_quantity(stop_distance=-5, equity=100_000, risk_pct=1.0) == 0


def test_sizer_very_small_equity_returns_zero() -> None:
    assert calculate_quantity(stop_distance=100, equity=0.5, risk_pct=1.0) == 0


def test_sizer_no_lot_size_returns_raw() -> None:
    qty = calculate_quantity(stop_distance=10, equity=100_000, risk_pct=1.0, lot_size=None)
    assert qty == 100


# ---------------------------------------------------------------------------
# Controller fixtures
# ---------------------------------------------------------------------------


def make_settings(**overrides: object) -> Settings:
    base = dict(
        zerodha_api_key="key",
        zerodha_api_secret="secret",
        zerodha_access_token="token",
        postgres_url="postgresql+asyncpg://u:p@localhost/t",
        redis_url="redis://localhost",
        risk_per_trade_pct=1.0,
        max_daily_loss_pct=2.0,
        # Explicitly pin paper_trading=False so the daily-loss-limit check runs
        # regardless of any PAPER_TRADING env var set in the developer's .env.
        paper_trading=False,
        # Use 23:59 so tests never fail due to time-of-day regardless of when they run.
        # Tests that explicitly check the cutoff rule override these values.
        intraday_cutoff_hour=23,
        intraday_cutoff_minute=59,
    )
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def make_signal(**overrides: object) -> SignalEvent:
    base = dict(
        signal_id=uuid4(),
        strategy_id="ema_cross",
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        signal_type=SignalType.ENTRY,
        stop_distance=10.0,
        timestamp=NOW,
        tick_log_id=1,  # required field — use a sentinel value in tests
    )
    return SignalEvent(**{**base, **overrides})  # type: ignore[arg-type]


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> MessageBus:
    return RedisMessageBus(fake_redis)


def make_controller(
    engine: AsyncEngine,
    bus: MessageBus,
    settings: Settings | None = None,
    equity: float = 100_000.0,
) -> DefaultRiskController:
    sf = build_session_factory(engine)
    s = settings or make_settings()
    return DefaultRiskController(bus, Repository(), sf, s, equity=equity)


# ---------------------------------------------------------------------------
# ABC / extensibility tests
# ---------------------------------------------------------------------------


def test_risk_controller_is_abstract() -> None:
    """RiskController cannot be instantiated directly."""
    import pytest

    with pytest.raises(TypeError):
        RiskController(  # type: ignore[abstract]
            bus=None,  # type: ignore[arg-type]
            repo=None,  # type: ignore[arg-type]
            session_factory=None,  # type: ignore[arg-type]
        )


async def test_custom_risk_controller_wires_and_passes_signals(
    engine: AsyncEngine, bus: MessageBus
) -> None:
    """A custom RiskController subclass that always accepts signals."""
    from trading.core.schemas import OrderType

    class AlwaysAccept(RiskController):
        async def _evaluate_signal(self, event: SignalEvent) -> ValidatedOrderEvent | str:
            return ValidatedOrderEvent(
                signal_id=event.signal_id,
                symbol=event.symbol,
                instrument_type=event.instrument_type,
                side=event.side,
                quantity=10,
                order_type=OrderType.MARKET,
                limit_price=None,
                tick_log_id=event.tick_log_id,
            )

    sf = build_session_factory(engine)
    ctrl = AlwaysAccept(bus, Repository(), sf)

    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].quantity == 10

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Controller — valid signal passes
# ---------------------------------------------------------------------------


async def test_valid_signal_publishes_validated_order(engine: AsyncEngine, bus: MessageBus) -> None:
    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].quantity > 0

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Time cutoff
# ---------------------------------------------------------------------------


async def test_after_cutoff_rejects_signal(engine: AsyncEngine, bus: MessageBus) -> None:
    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    # Set cutoff to 00:00 so any signal today is "after cutoff"
    settings = make_settings(intraday_cutoff_hour=0, intraday_cutoff_minute=0)
    ctrl = make_controller(engine, bus, settings=settings)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    assert len(received) == 0  # rejected

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


async def test_circuit_open_rejects_signal(engine: AsyncEngine, bus: MessageBus) -> None:
    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.set_flag("circuit:ingestor:open", "1")
    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    assert len(received) == 0

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Daily loss limit
# ---------------------------------------------------------------------------


async def test_daily_loss_limit_rejects_signal(engine: AsyncEngine, bus: MessageBus) -> None:
    """Insert a large filled order so realized P&L exceeds 2% of equity."""
    from trading.core.database import get_session

    sig_id = uuid4()
    async with get_session(engine) as s:
        s.add(
            Signal(
                id=sig_id,
                strategy_id="s",
                symbol="INFY",
                instrument_type="EQUITY",
                side="SELL",
                signal_type="ENTRY",
                stop_distance=Decimal("10"),
                created_at=NOW,
            )
        )

    # P&L = 10*1000 = 10_000, limit = 100_000 * 2% = 2_000 → exceeded
    async with get_session(engine) as s:
        s.add(
            Order(
                id=uuid4(),
                kite_order_id="K_LOSS",
                signal_id=sig_id,
                status=OrderStatus.FILLED.value,
                qty=10,
                avg_price=Decimal("1000"),
                created_at=NOW,
            )
        )

    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus, equity=100_000.0)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    assert len(received) == 0

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Position check
# ---------------------------------------------------------------------------


async def test_entry_with_existing_position_rejected(engine: AsyncEngine, bus: MessageBus) -> None:
    from trading.core.database import get_session

    # Pre-insert an open position
    async with get_session(engine) as s:
        s.add(
            Position(
                symbol="INFY",
                instrument_type="EQUITY",
                net_qty=10,
                avg_price=Decimal("1500"),
                updated_at=NOW,
            )
        )

    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal(signal_type=SignalType.ENTRY))
    await asyncio.sleep(0.1)

    assert len(received) == 0

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_exit_with_existing_position_passes(engine: AsyncEngine, bus: MessageBus) -> None:
    """EXIT signals bypass the duplicate-position check."""
    from trading.core.database import get_session

    async with get_session(engine) as s:
        s.add(
            Position(
                symbol="INFY",
                instrument_type="EQUITY",
                net_qty=10,
                avg_price=Decimal("1500"),
                updated_at=NOW,
            )
        )

    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal(signal_type=SignalType.EXIT, side=Side.SELL))
    await asyncio.sleep(0.1)

    assert len(received) == 1  # EXIT passed

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Zero quantity
# ---------------------------------------------------------------------------


async def test_zero_quantity_rejects_signal(engine: AsyncEngine, bus: MessageBus) -> None:
    """stop_distance so large that no shares can be afforded."""
    received: list[ValidatedOrderEvent] = []
    bus.subscribe(
        "validated_orders", ValidatedOrderEvent, lambda e: received.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]

    ctrl = make_controller(engine, bus, equity=100.0)  # tiny equity
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    # risk=1% of 100 = 1, stop=50 → qty=0
    await bus.publish("signals", make_signal(stop_distance=50.0))
    await asyncio.sleep(0.1)

    assert len(received) == 0

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Rejection audit logging
# ---------------------------------------------------------------------------


async def test_rejected_signal_logged_to_audit(engine: AsyncEngine, bus: MessageBus) -> None:
    from sqlalchemy import select

    from trading.core.database import get_session
    from trading.core.models import AuditLog

    settings = make_settings(intraday_cutoff_hour=0, intraday_cutoff_minute=0)
    ctrl = make_controller(engine, bus, settings=settings)
    task = asyncio.get_event_loop().create_task(ctrl.start())
    await asyncio.sleep(0.05)

    await bus.publish("signals", make_signal())
    await asyncio.sleep(0.1)

    async with get_session(engine) as s:
        result = await s.execute(select(AuditLog).where(AuditLog.module.like("risk_controller%")))
        logs = result.scalars().all()

    assert len(logs) >= 1
    assert any("rejected" in log.message for log in logs)

    await ctrl.stop()
    await asyncio.gather(task, return_exceptions=True)
