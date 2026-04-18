from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from anyio import sleep_forever
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.core.messaging import MessageBus
from trading.core.schemas import CandleEvent, InstrumentType, TickEvent
from trading.engine.component import Component
from trading.storage.repository import Repository

logger = logging.getLogger(__name__)

# Interval string → minutes (used for bar-boundary computation)
_INTERVAL_MINUTES: dict[str, int] = {
    "1min": 1,
    "3min": 3,
    "5min": 5,
    "10min": 10,
    "15min": 15,
    "30min": 30,
    "60min": 60,
}


@dataclass
class PartialBar:
    symbol: str
    instrument_type: InstrumentType
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    bar_open_time: datetime
    tick_log_id: int  # id of the last tick that updated/closed this bar


@dataclass
class _SymbolConfig:
    symbol: str
    instrument_token: int
    instrument_type: InstrumentType


class CandleAggregator(Component):
    """
    Aggregates ``TickEvent``s from Redis into OHLCV candles.

    On each tick the aggregator:
    - Opens a new ``PartialBar`` on the first tick in a bar window.
    - Updates H/L/C/volume on subsequent ticks in the same window.
    - Closes the bar and publishes a ``CandleEvent`` when a tick falls
      outside the current window, then immediately opens a new bar.

    tick_log_id propagation
    -----------------------
    ``tick_log_id`` flows from the originating ``TickEvent`` through the
    ``PartialBar`` and into every ``CandleEvent``. Downstream consumers
    (AlgoRunner, RiskController) carry it forward so every DecisionLog row
    can be traced back to its root tick.

    Warm-up
    -------
    On ``_setup()`` the aggregator fetches historical OHLC from the broker
    and re-publishes each candle as a ``CandleEvent`` so downstream consumers
    (feature engine, strategy) can prime their state before live ticks arrive.
    Warm-up candles use ``tick_log_id=0`` (no originating live tick).

    One subscriber task is spawned per (symbol, interval) pair.
    """

    def __init__(
        self,
        bus: MessageBus,
        broker: Broker,
        symbols: list[_SymbolConfig],
        intervals: list[str],
        session_factory: async_sessionmaker[AsyncSession],
        repo: Repository,
        warmup_count: int = 200,
    ) -> None:
        super().__init__(name="candle_aggregator")
        self._bus = bus
        self._broker = broker
        self._symbols = symbols
        self._intervals = intervals
        self._session_factory = session_factory
        self._repo = repo
        self._warmup_count = warmup_count

        # (symbol, interval) → current partial bar
        self._bars: dict[tuple[str, str], PartialBar] = {}
        # token → symbol lookup for tick routing
        self._token_symbol: dict[int, _SymbolConfig] = {sc.instrument_token: sc for sc in symbols}

    # ------------------------------------------------------------------
    # Component lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        await self._warmup()
        for sc in self._symbols:
            self._bus.subscribe(
                f"tick:{sc.instrument_token}",
                TickEvent,
                self._on_tick,
            )
        logger.info(
            "CandleAggregator: subscribed to %d symbols × %d intervals",
            len(self._symbols),
            len(self._intervals),
        )

    async def _run(self) -> None:
        await sleep_forever()

    # ------------------------------------------------------------------
    # Warm-up: replay historical candles before live ticks arrive
    # ------------------------------------------------------------------

    async def _warmup(self) -> None:
        from datetime import timedelta

        now = datetime.now(UTC)
        max_minutes = max((_INTERVAL_MINUTES.get(iv, 1) for iv in self._intervals), default=1)
        lookback_hours = (self._warmup_count * max_minutes) // 60 + 24
        start = now - timedelta(hours=lookback_hours)

        for sc in self._symbols:
            for interval in self._intervals:
                try:
                    df = self._broker.get_ohlc(sc.symbol, interval, start, now)
                except Exception as exc:
                    logger.warning(
                        "CandleAggregator: warm-up failed for %s %s — %s",
                        sc.symbol,
                        interval,
                        exc,
                    )
                    continue

                if df.is_empty():
                    logger.debug(
                        "CandleAggregator: no warm-up data for %s %s",
                        sc.symbol,
                        interval,
                    )
                    continue

                rows = df.tail(self._warmup_count)
                for row in rows.iter_rows(named=True):
                    try:
                        event = CandleEvent(
                            symbol=sc.symbol,
                            instrument_type=sc.instrument_type,
                            interval=interval,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row.get("volume", 0)),
                            timestamp=_ensure_utc(row["date"]),
                            tick_log_id=0,  # historical — no originating live tick
                        )
                        await self._bus.publish(f"candle:{sc.symbol}:{interval}", event)
                    except Exception as exc:
                        logger.warning(
                            "CandleAggregator: invalid warm-up row for %s %s — %s",
                            sc.symbol,
                            interval,
                            exc,
                        )

        logger.info("CandleAggregator: warm-up complete")

    # ------------------------------------------------------------------
    # Live tick → bar aggregation
    # ------------------------------------------------------------------

    async def _on_tick(self, event: TickEvent) -> None:
        sc = self._token_symbol.get(event.instrument_token)
        if sc is None:
            return

        for interval in self._intervals:
            await self._process_tick(sc, interval, event)

    async def _process_tick(self, sc: _SymbolConfig, interval: str, event: TickEvent) -> None:
        key = (sc.symbol, interval)
        bar_open = _bar_open_time(event.timestamp, interval)

        existing = self._bars.get(key)
        if existing is None:
            self._bars[key] = _new_bar(sc, interval, event, bar_open)
            return

        if bar_open > existing.bar_open_time:
            # Tick falls in a new bar window: close existing, open new
            # Update the closing bar's tick_log_id to the tick that triggered the close
            existing.tick_log_id = event.tick_log_id
            await self._emit(existing)
            self._bars[key] = _new_bar(sc, interval, event, bar_open)
        else:
            # Same bar window — update H/L/C/volume and track latest tick id
            existing.high = max(existing.high, event.last_price)
            existing.low = min(existing.low, event.last_price)
            existing.close = event.last_price
            existing.volume += event.volume
            existing.tick_log_id = event.tick_log_id

    async def _emit(self, bar: PartialBar) -> None:
        minutes = _INTERVAL_MINUTES.get(bar.interval, 1)
        from datetime import timedelta

        bar_close = bar.bar_open_time + timedelta(minutes=minutes)
        event = CandleEvent(
            symbol=bar.symbol,
            instrument_type=bar.instrument_type,
            interval=bar.interval,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            timestamp=bar_close,
            tick_log_id=bar.tick_log_id,  # propagated from the originating tick
        )
        await self._bus.publish(f"candle:{bar.symbol}:{bar.interval}", event)

        # Log the CANDLE_EMITTED decision (fire-and-forget — audit trail only)
        asyncio.get_running_loop().create_task(self._log_candle_decision(event))

    async def _log_candle_decision(self, event: CandleEvent) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.log_decision(
                        session,
                        step="CANDLE_EMITTED",
                        symbol=event.symbol,
                        tick_log_id=event.tick_log_id,
                        context={
                            "interval": event.interval,
                            "open": event.open,
                            "high": event.high,
                            "low": event.low,
                            "close": event.close,
                            "volume": event.volume,
                            "candle_ts": event.timestamp.isoformat(),
                        },
                    )
        except Exception:
            logger.warning(
                "CandleAggregator: decision log failed for %s %s — audit trail gap",
                event.symbol,
                event.interval,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bar_open_time(ts: datetime, interval: str) -> datetime:
    """Return the open timestamp of the bar containing *ts*."""
    minutes = _INTERVAL_MINUTES.get(interval, 1)
    total_minutes = ts.hour * 60 + ts.minute
    floored = (total_minutes // minutes) * minutes
    bar_hour, bar_minute = divmod(floored, 60)
    return ts.replace(hour=bar_hour, minute=bar_minute, second=0, microsecond=0)


def _new_bar(sc: _SymbolConfig, interval: str, event: TickEvent, bar_open: datetime) -> PartialBar:
    return PartialBar(
        symbol=sc.symbol,
        instrument_type=sc.instrument_type,
        interval=interval,
        open=event.last_price,
        high=event.last_price,
        low=event.last_price,
        close=event.last_price,
        volume=event.volume,
        bar_open_time=bar_open,
        tick_log_id=event.tick_log_id,
    )


def _ensure_utc(dt: object) -> datetime:
    """Coerce broker-returned datetime (may be naive) to UTC-aware."""
    if isinstance(dt, datetime):
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    raise TypeError(f"Expected datetime, got {type(dt)}")
