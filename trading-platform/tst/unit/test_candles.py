"""Tests for data/candles.py — CandleAggregator"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import polars as pl
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from trading.broker.base.broker import Broker
from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus, RedisMessageBus
from trading.core.schemas import CandleEvent, InstrumentType, TickEvent
from trading.data.candles import CandleAggregator, _bar_open_time, _SymbolConfig
from trading.storage.repository import Repository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2025, 1, 6, 9, 15, 0, tzinfo=UTC)  # Monday 09:15 IST


def t(offset_seconds: float) -> datetime:
    """Return a timestamp offset from BASE_TIME."""
    return BASE_TIME + timedelta(seconds=offset_seconds)


def tick(token: int, price: float, ts: datetime, volume: int = 100) -> TickEvent:
    return TickEvent(
        instrument_token=token,
        instrument_type=InstrumentType.EQUITY,
        last_price=price,
        volume=volume,
        timestamp=ts,
        tick_log_id=0,
    )


def make_ohlc_df(n: int, start: datetime, interval_mins: int = 1) -> pl.DataFrame:
    """Create a synthetic OHLCV DataFrame with n rows."""
    rows = []
    for i in range(n):
        ts = start + timedelta(minutes=i * interval_mins)
        price = 100.0 + i
        rows.append(
            {
                "date": ts,
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price + 0.5,
                "volume": 1000 + i,
            }
        )
    return pl.DataFrame(rows)


# ---------------------------------------------------------------------------
# MockBroker
# ---------------------------------------------------------------------------


class MockBroker(Broker):
    """Returns a pre-configured DataFrame on get_ohlc(); can raise."""

    def __init__(self, df: pl.DataFrame | None = None, raises: bool = False) -> None:
        self._df = df if df is not None else pl.DataFrame()
        self._raises = raises
        self.calls: list[tuple[str, str]] = []

    def get_instruments(self) -> pl.DataFrame:
        return pl.DataFrame()

    async def place_order(self, symbol, side, qty, order_type, limit_price=None) -> str:  # type: ignore[override]
        return "MOCK_ORDER"

    def get_ohlc(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        self.calls.append((symbol, interval))
        if self._raises:
            raise RuntimeError("broker unavailable")
        return self._df


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> MessageBus:
    return RedisMessageBus(fake_redis)


@pytest.fixture
async def engine() -> AsyncEngine:  # type: ignore[misc]
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(eng)
    yield eng
    await eng.dispose()


def make_aggregator(
    bus: MessageBus,
    broker: MockBroker,
    engine: AsyncEngine,
    tokens: list[int] | None = None,
    intervals: list[str] | None = None,
    warmup_count: int = 5,
) -> CandleAggregator:
    tokens = tokens or [1]
    intervals = intervals or ["1min"]
    symbols = [
        _SymbolConfig(symbol=f"SYM{t}", instrument_token=t, instrument_type=InstrumentType.EQUITY)
        for t in tokens
    ]
    sf = build_session_factory(engine)
    return CandleAggregator(
        bus,
        broker,
        symbols,
        intervals,
        session_factory=sf,
        repo=Repository(),
        warmup_count=warmup_count,
    )


# ---------------------------------------------------------------------------
# Bar open time helper
# ---------------------------------------------------------------------------


def test_bar_open_time_1min() -> None:
    ts = datetime(2025, 1, 6, 9, 17, 35, tzinfo=UTC)
    assert _bar_open_time(ts, "1min") == datetime(2025, 1, 6, 9, 17, 0, tzinfo=UTC)


def test_bar_open_time_5min() -> None:
    ts = datetime(2025, 1, 6, 9, 17, 0, tzinfo=UTC)
    assert _bar_open_time(ts, "5min") == datetime(2025, 1, 6, 9, 15, 0, tzinfo=UTC)


def test_bar_open_time_15min() -> None:
    ts = datetime(2025, 1, 6, 9, 29, 59, tzinfo=UTC)
    assert _bar_open_time(ts, "15min") == datetime(2025, 1, 6, 9, 15, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Bar aggregation — unit tests (no component lifecycle)
# ---------------------------------------------------------------------------


async def test_first_tick_initialises_bar(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    received: list[CandleEvent] = []
    bus.subscribe("candle:SYM1:1min", CandleEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    await agg._on_tick(tick(1, 100.0, t(0)))
    assert ("SYM1", "1min") in agg._bars
    bar = agg._bars[("SYM1", "1min")]
    assert bar.open == bar.high == bar.low == bar.close == 100.0
    assert bar.volume == 100

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_higher_price_tick_updates_high(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    await agg._on_tick(tick(1, 100.0, t(0)))
    await agg._on_tick(tick(1, 110.0, t(10)))

    bar = agg._bars[("SYM1", "1min")]
    assert bar.high == 110.0
    assert bar.low == 100.0
    assert bar.close == 110.0

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_lower_price_tick_updates_low(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    await agg._on_tick(tick(1, 100.0, t(0)))
    await agg._on_tick(tick(1, 90.0, t(10)))

    bar = agg._bars[("SYM1", "1min")]
    assert bar.low == 90.0
    assert bar.high == 100.0

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_volume_accumulates_within_bar(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    await agg._on_tick(tick(1, 100.0, t(0), volume=50))
    await agg._on_tick(tick(1, 101.0, t(10), volume=75))

    bar = agg._bars[("SYM1", "1min")]
    assert bar.volume == 125

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_tick_crossing_bar_boundary_emits_candle(
    bus: MessageBus, engine: AsyncEngine
) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    received: list[CandleEvent] = []
    bus.subscribe("candle:SYM1:1min", CandleEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    await asyncio.sleep(0.05)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    # Both at 09:15 — same bar
    await agg._on_tick(tick(1, 100.0, BASE_TIME))
    await agg._on_tick(tick(1, 105.0, BASE_TIME + timedelta(seconds=30)))
    # 09:16 — new bar → emits previous
    await agg._on_tick(tick(1, 110.0, BASE_TIME + timedelta(minutes=1)))
    await asyncio.sleep(0.05)

    assert len(received) == 1
    candle = received[0]
    assert candle.open == 100.0
    assert candle.high == 105.0
    assert candle.close == 105.0
    assert candle.symbol == "SYM1"
    assert candle.interval == "1min"

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_two_intervals_track_independently(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine, intervals=["1min", "5min"])

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    received_1m: list[CandleEvent] = []
    received_5m: list[CandleEvent] = []
    bus.subscribe(
        "candle:SYM1:1min", CandleEvent, lambda e: received_1m.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]
    bus.subscribe(
        "candle:SYM1:5min", CandleEvent, lambda e: received_5m.append(e) or asyncio.sleep(0)
    )  # type: ignore[return-value]
    await asyncio.sleep(0.05)  # let subscribers actually subscribe to Redis

    # Two ticks in the 09:15 window
    await agg._on_tick(tick(1, 100.0, BASE_TIME))
    await agg._on_tick(tick(1, 102.0, BASE_TIME + timedelta(seconds=30)))

    # 09:16 — crosses 1min but stays in 5min
    await agg._on_tick(tick(1, 104.0, BASE_TIME + timedelta(minutes=1)))
    await asyncio.sleep(0.05)

    # 1min bar closed; 5min bar still open
    assert len(received_1m) == 1
    assert len(received_5m) == 0

    # Both bars in the _bars dict
    assert ("SYM1", "1min") in agg._bars
    assert ("SYM1", "5min") in agg._bars

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_zero_volume_tick_updates_ohlc(bus: MessageBus, engine: AsyncEngine) -> None:
    """volume=0 is valid (Zerodha sends it on auction)."""
    broker = MockBroker()
    agg = make_aggregator(bus, broker, engine)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.05)

    await agg._on_tick(tick(1, 100.0, t(0), volume=0))
    bar = agg._bars[("SYM1", "1min")]
    assert bar.volume == 0
    assert bar.open == 100.0

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Warm-up
# ---------------------------------------------------------------------------


async def test_warmup_publishes_historical_candles(bus: MessageBus, engine: AsyncEngine) -> None:
    df = make_ohlc_df(10, BASE_TIME - timedelta(hours=1))
    broker = MockBroker(df=df)
    agg = make_aggregator(bus, broker, engine, warmup_count=10)

    received: list[CandleEvent] = []
    bus.subscribe("candle:SYM1:1min", CandleEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    await asyncio.sleep(0.05)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.1)

    assert len(received) == 10

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_warmup_empty_result_no_crash(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker(df=pl.DataFrame())
    agg = make_aggregator(bus, broker, engine, warmup_count=5)

    received: list[CandleEvent] = []
    bus.subscribe("candle:SYM1:1min", CandleEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    await asyncio.sleep(0.05)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.1)

    assert len(received) == 0  # no crash

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_warmup_broker_failure_no_crash(bus: MessageBus, engine: AsyncEngine) -> None:
    broker = MockBroker(raises=True)
    agg = make_aggregator(bus, broker, engine, warmup_count=5)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.1)

    # Should reach RUNNING state despite broker failure
    from trading.engine.component import ComponentState

    assert agg.state == ComponentState.RUNNING

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)


async def test_warmup_respects_warmup_count(bus: MessageBus, engine: AsyncEngine) -> None:
    """Only last warmup_count rows are published, even if broker returns more."""
    df = make_ohlc_df(50, BASE_TIME - timedelta(hours=1))
    broker = MockBroker(df=df)
    agg = make_aggregator(bus, broker, engine, warmup_count=20)

    received: list[CandleEvent] = []
    bus.subscribe("candle:SYM1:1min", CandleEvent, lambda e: received.append(e) or asyncio.sleep(0))  # type: ignore[return-value]
    await asyncio.sleep(0.05)

    task = asyncio.get_event_loop().create_task(agg.start())
    await asyncio.sleep(0.1)

    assert len(received) == 20

    await agg.stop()
    await asyncio.gather(task, return_exceptions=True)
