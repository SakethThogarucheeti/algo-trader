"""Tests for storage/repository.py"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.core.database import get_session, init_db
from trading.core.models import Instrument, Order, Signal
from trading.core.schemas import (
    FillEvent,
    InstrumentType,
    OrderStatus,
    Side,
    SignalEvent,
    SignalType,
)
from trading.storage.repository import NotFoundError, Repository

NOW = datetime.now(UTC)
TODAY = NOW.date()

repo = Repository()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


def make_signal_event(**overrides: object) -> SignalEvent:
    base = dict(
        signal_id=uuid4(),
        strategy_id="ema_cross",
        symbol="INFY",
        instrument_type=InstrumentType.EQUITY,
        side=Side.BUY,
        signal_type=SignalType.ENTRY,
        stop_distance=10.0,
        timestamp=NOW,
        tick_log_id=1,
    )
    return SignalEvent(**{**base, **overrides})  # type: ignore[arg-type]


def make_fill(**overrides: object) -> FillEvent:
    base = dict(
        kite_order_id="K001",
        avg_price=100.0,
        filled_qty=10,
        timestamp=NOW,
    )
    return FillEvent(**{**base, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------


async def test_get_instrument_returns_none_for_missing(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        result = await repo.get_instrument(s, 9999)
    assert result is None


async def test_upsert_and_get_instrument(engine: AsyncEngine) -> None:
    inst = Instrument(token=1, symbol="INFY", exchange="NSE", instrument_type="EQUITY")
    async with get_session(engine) as s:
        await repo.upsert_instruments(s, [inst])

    async with get_session(engine) as s:
        fetched = await repo.get_instrument(s, 1)
    assert fetched is not None
    assert fetched.symbol == "INFY"


async def test_upsert_updates_existing_instrument(engine: AsyncEngine) -> None:
    inst = Instrument(token=2, symbol="TCS", exchange="NSE", instrument_type="EQUITY")
    async with get_session(engine) as s:
        await repo.upsert_instruments(s, [inst])

    updated = Instrument(token=2, symbol="TCS", exchange="BSE", instrument_type="EQUITY")
    async with get_session(engine) as s:
        await repo.upsert_instruments(s, [updated])

    async with get_session(engine) as s:
        fetched = await repo.get_instrument(s, 2)
    assert fetched is not None
    assert fetched.exchange == "BSE"


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


async def test_save_signal_persists(engine: AsyncEngine) -> None:
    event = make_signal_event()
    async with get_session(engine) as s:
        await repo.save_signal(s, event)

    async with get_session(engine) as s:
        sig = await s.get(Signal, event.signal_id)
    assert sig is not None
    assert sig.strategy_id == "ema_cross"
    assert sig.symbol == "INFY"


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


async def _insert_signal(engine: AsyncEngine, sig_id: object = None) -> object:
    if sig_id is None:
        sig_id = uuid4()
    event = make_signal_event(signal_id=sig_id)
    async with get_session(engine) as s:
        await repo.save_signal(s, event)
    return sig_id


async def test_save_and_get_order(engine: AsyncEngine) -> None:
    sig_id = await _insert_signal(engine)
    order = Order(
        id=uuid4(),
        kite_order_id="K100",
        signal_id=sig_id,
        status=OrderStatus.PLACED.value,
        qty=5,
        avg_price=Decimal("0"),
        created_at=NOW,
    )
    async with get_session(engine) as s:
        await repo.save_order(s, order)

    async with get_session(engine) as s:
        fetched = await repo.get_order_by_kite_id(s, "K100")
    assert fetched is not None
    assert fetched.qty == 5


async def test_get_order_by_kite_id_missing_returns_none(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        result = await repo.get_order_by_kite_id(s, "NONEXISTENT")
    assert result is None


async def test_update_order_status(engine: AsyncEngine) -> None:
    sig_id = await _insert_signal(engine)
    async with get_session(engine) as s:
        await repo.save_order(
            s,
            Order(
                id=uuid4(),
                kite_order_id="K200",
                signal_id=sig_id,
                status=OrderStatus.PLACED.value,
                qty=10,
                avg_price=Decimal("0"),
                created_at=NOW,
            ),
        )

    async with get_session(engine) as s:
        await repo.update_order_status(s, "K200", OrderStatus.FILLED, avg_price=150.0)

    async with get_session(engine) as s:
        order = await repo.get_order_by_kite_id(s, "K200")
    assert order is not None
    assert order.status == OrderStatus.FILLED.value
    assert float(order.avg_price) == 150.0


async def test_update_order_status_missing_raises(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        with pytest.raises(NotFoundError):
            await repo.update_order_status(s, "GHOST", OrderStatus.FILLED)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


async def test_get_position_missing_returns_none(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        result = await repo.get_position(s, "INFY", "EQUITY")
    assert result is None


async def test_update_position_creates_on_first_buy(engine: AsyncEngine) -> None:
    fill = make_fill(avg_price=100.0, filled_qty=10)
    async with get_session(engine) as s:
        await repo.update_position(s, fill, Side.BUY, "INFY", "EQUITY")

    async with get_session(engine) as s:
        pos = await repo.get_position(s, "INFY", "EQUITY")
    assert pos is not None
    assert pos.net_qty == 10
    assert float(pos.avg_price) == 100.0


async def test_update_position_adds_to_existing_long(engine: AsyncEngine) -> None:
    fill1 = make_fill(avg_price=100.0, filled_qty=10)
    fill2 = make_fill(avg_price=110.0, filled_qty=10)

    async with get_session(engine) as s:
        await repo.update_position(s, fill1, Side.BUY, "TCS", "EQUITY")
    async with get_session(engine) as s:
        await repo.update_position(s, fill2, Side.BUY, "TCS", "EQUITY")

    async with get_session(engine) as s:
        pos = await repo.get_position(s, "TCS", "EQUITY")
    assert pos is not None
    assert pos.net_qty == 20
    assert float(pos.avg_price) == pytest.approx(105.0)


async def test_update_position_sell_reduces_qty(engine: AsyncEngine) -> None:
    fill_buy = make_fill(avg_price=100.0, filled_qty=10)
    fill_sell = make_fill(avg_price=120.0, filled_qty=10)

    async with get_session(engine) as s:
        await repo.update_position(s, fill_buy, Side.BUY, "RELIANCE", "EQUITY")
    async with get_session(engine) as s:
        await repo.update_position(s, fill_sell, Side.SELL, "RELIANCE", "EQUITY")

    async with get_session(engine) as s:
        pos = await repo.get_position(s, "RELIANCE", "EQUITY")
    assert pos is not None
    assert pos.net_qty == 0


async def test_update_position_sell_goes_short(engine: AsyncEngine) -> None:
    """Selling more than owned (futures short) produces negative net_qty."""
    fill_buy = make_fill(avg_price=100.0, filled_qty=10)
    fill_sell = make_fill(avg_price=90.0, filled_qty=15)

    async with get_session(engine) as s:
        await repo.update_position(s, fill_buy, Side.BUY, "NIFTY", "FUTURES")
    async with get_session(engine) as s:
        await repo.update_position(s, fill_sell, Side.SELL, "NIFTY", "FUTURES")

    async with get_session(engine) as s:
        pos = await repo.get_position(s, "NIFTY", "FUTURES")
    assert pos is not None
    assert pos.net_qty == -5
    assert float(pos.avg_price) == 90.0  # new avg is the fill price when short


async def test_position_composite_pk_independent(engine: AsyncEngine) -> None:
    """INFY EQUITY and INFY FUTURES are tracked independently."""
    fill = make_fill(avg_price=1500.0, filled_qty=5)
    async with get_session(engine) as s:
        await repo.update_position(s, fill, Side.BUY, "INFY", "EQUITY")
    fill2 = make_fill(avg_price=1510.0, filled_qty=75)
    async with get_session(engine) as s:
        await repo.update_position(s, fill2, Side.BUY, "INFY", "FUTURES")

    async with get_session(engine) as s:
        eq = await repo.get_position(s, "INFY", "EQUITY")
        fut = await repo.get_position(s, "INFY", "FUTURES")
    assert eq is not None and eq.net_qty == 5
    assert fut is not None and fut.net_qty == 75


# ---------------------------------------------------------------------------
# Daily P&L
# ---------------------------------------------------------------------------


async def test_get_daily_realized_pnl_returns_zero_for_no_fills(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        pnl = await repo.get_daily_realized_pnl(s, TODAY)
    assert pnl == 0.0


async def test_get_daily_realized_pnl_sums_filled_orders(engine: AsyncEngine) -> None:
    sig_id = await _insert_signal(engine)
    # Two filled orders today
    async with get_session(engine) as s:
        s.add(
            Order(
                id=uuid4(),
                kite_order_id="K301",
                signal_id=sig_id,
                status=OrderStatus.FILLED.value,
                qty=10,
                avg_price=Decimal("100"),
                created_at=NOW,
            )
        )
        s.add(
            Order(
                id=uuid4(),
                kite_order_id="K302",
                signal_id=sig_id,
                status=OrderStatus.FILLED.value,
                qty=5,
                avg_price=Decimal("200"),
                created_at=NOW,
            )
        )
        # PLACED order — should NOT count
        s.add(
            Order(
                id=uuid4(),
                kite_order_id="K303",
                signal_id=sig_id,
                status=OrderStatus.PLACED.value,
                qty=20,
                avg_price=Decimal("150"),
                created_at=NOW,
            )
        )

    async with get_session(engine) as s:
        pnl = await repo.get_daily_realized_pnl(s, TODAY)
    # 10*100 + 5*200 = 2000
    assert pnl == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Heartbeats
# ---------------------------------------------------------------------------


async def test_update_heartbeat_creates_entry(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        await repo.update_heartbeat(s, "ingestor")

    async with get_session(engine) as s:
        from trading.core.models import Heartbeat

        hb = await s.get(Heartbeat, "ingestor")
    assert hb is not None


async def test_update_heartbeat_upserts(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        await repo.update_heartbeat(s, "candle_aggregator")

    async with get_session(engine) as s:
        await repo.update_heartbeat(s, "candle_aggregator")  # second call, same module

    async with get_session(engine) as s:
        from sqlalchemy import func, select

        from trading.core.models import Heartbeat

        count = await s.execute(select(func.count()).where(Heartbeat.module == "candle_aggregator"))
    assert count.scalar() == 1  # only one row, not two


async def test_get_stale_modules_empty_when_fresh(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        await repo.update_heartbeat(s, "executor")

    async with get_session(engine) as s:
        stale = await repo.get_stale_modules(s, timeout_secs=60)
    assert "executor" not in stale


async def test_get_stale_modules_detects_old_heartbeat(engine: AsyncEngine) -> None:
    from trading.core.models import Heartbeat

    old_ts = datetime.now(UTC) - timedelta(seconds=120)
    async with get_session(engine) as s:
        s.add(Heartbeat(module="zombie", last_seen=old_ts))

    async with get_session(engine) as s:
        stale = await repo.get_stale_modules(s, timeout_secs=60)
    assert "zombie" in stale


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


async def test_log_audit_appends(engine: AsyncEngine) -> None:
    async with get_session(engine) as s:
        await repo.log_audit(s, "risk", "WARNING", "daily loss limit hit")
        await repo.log_audit(s, "risk", "INFO", "signal rejected")

    async with get_session(engine) as s:
        from sqlalchemy import select

        from trading.core.models import AuditLog

        result = await s.execute(select(AuditLog))
        logs = result.scalars().all()
    assert len(logs) == 2
    messages = {log.message for log in logs}
    assert "daily loss limit hit" in messages
    assert "signal rejected" in messages


async def test_log_audit_never_raises_on_repeated_calls(engine: AsyncEngine) -> None:
    for i in range(5):
        async with get_session(engine) as s:
            await repo.log_audit(s, "monitor", "INFO", f"heartbeat {i}")
    # no exception raised


# ---------------------------------------------------------------------------
# AlgoConfig / AlgoState
# ---------------------------------------------------------------------------


async def test_seed_algo_config_creates_new(engine: AsyncEngine) -> None:
    from trading.core.models import AlgoConfig as AlgoConfigModel
    async with get_session(engine) as s:
        await repo.seed_algo_config(
            s, name="test_algo", strategy_id="ema_crossover",
            warmup_candles=200, candle_intervals=["1min"],
            equity=10_000.0, params={"fast": 9},
        )

    async with get_session(engine) as s:
        cfg = await s.get(AlgoConfigModel, "test_algo")
    assert cfg is not None
    assert cfg.strategy_id == "ema_crossover"


async def test_seed_algo_config_skips_existing(engine: AsyncEngine) -> None:
    """Calling seed_algo_config twice should not overwrite or error."""
    from trading.core.models import AlgoConfig as AlgoConfigModel
    async with get_session(engine) as s:
        await repo.seed_algo_config(
            s, name="dup_algo", strategy_id="ema_crossover",
            warmup_candles=200, candle_intervals=["1min"],
            equity=10_000.0, params={},
        )
    async with get_session(engine) as s:
        await repo.seed_algo_config(
            s, name="dup_algo", strategy_id="rsi_mean_reversion",  # changed
            warmup_candles=100, candle_intervals=["5min"],
            equity=5_000.0, params={},
        )

    async with get_session(engine) as s:
        cfg = await s.get(AlgoConfigModel, "dup_algo")
    assert cfg is not None
    assert cfg.strategy_id == "ema_crossover"  # original preserved


async def test_upsert_algo_state_insert_then_update(engine: AsyncEngine) -> None:
    """First call inserts; second call updates the existing row."""
    from trading.core.models import AlgoState as AlgoStateModel
    async with get_session(engine) as s:
        await repo.upsert_algo_state(s, "my:INFY", {"bars_seen": 1})

    async with get_session(engine) as s:
        state = await s.get(AlgoStateModel, "my:INFY")
    assert state is not None
    assert json.loads(state.state)["bars_seen"] == 1

    async with get_session(engine) as s:
        await repo.upsert_algo_state(s, "my:INFY", {"bars_seen": 42})

    async with get_session(engine) as s:
        state = await s.get(AlgoStateModel, "my:INFY")
    assert state is not None
    assert json.loads(state.state)["bars_seen"] == 42


async def test_get_algo_configs_with_state(engine: AsyncEngine) -> None:
    from trading.core.models import AlgoConfig as AlgoConfigModel, AlgoState as AlgoStateModel
    async with get_session(engine) as s:
        s.add(AlgoConfigModel(
            name="cfg1", strategy_id="ema_crossover", warmup_candles=200,
            candle_intervals=json.dumps(["1min"]), equity=10_000.0, params=json.dumps({"fast": 9}),
        ))
        s.add(AlgoStateModel(name="cfg1", state=json.dumps({"bars_seen": 10})))
        s.add(AlgoConfigModel(
            name="cfg2", strategy_id="rsi_mean_reversion", warmup_candles=100,
            candle_intervals=json.dumps(["5min"]), equity=5_000.0, params=json.dumps({}),
        ))
        # cfg2 has no AlgoState row

    async with get_session(engine) as s:
        results = await repo.get_algo_configs_with_state(s)

    assert len(results) == 2
    by_name = {r["name"]: r for r in results}
    assert by_name["cfg1"]["state"]["bars_seen"] == 10
    assert by_name["cfg2"]["state"] == {}
    assert by_name["cfg2"]["updated_at"] is None
