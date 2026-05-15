from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from trading.broker.base.broker import Broker
from trading.core.messaging import AbstractRegistry
from trading.core.models import Instrument
from trading.core.schemas import CandleEvent, InstrumentType, TickEvent
from trading.core.tasks import fire
from trading.indicators.types import CandleRow
from trading.storage.stores.audit import AbstractAuditStore
from trading.storage.stores.candle import AbstractCandleDataStore

logger = logging.getLogger(__name__)

_INTERVAL_MINUTES: dict[str, int] = {
    "1min": 1,
    "3min": 3,
    "5min": 5,
    "10min": 10,
    "15min": 15,
    "30min": 30,
    "60min": 60,
}

# NSE trades ~375 min/day (9:15–15:30); 5 trading days per 7 calendar days.
# Multiply trading-time lookback by this factor to get a calendar-time window
# that reliably contains enough bars across weekends and market holidays.
_CALENDAR_MINUTES_PER_TRADING_MINUTE = (7 / 5) * (1440 / 375)  # ≈ 5.4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    tick_log_id: int


@dataclass
class _SymbolConfig:
    symbol: str
    instrument_token: int
    instrument_type: InstrumentType


def _bar_open_time(ts: datetime, interval: str) -> datetime:
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
    if isinstance(dt, datetime):
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    raise TypeError(f"Expected datetime, got {type(dt)}")


class CandleConfig(BaseModel):
    """Configuration for the candle aggregation stage."""

    model_config = {"arbitrary_types_allowed": True}

    instruments: list[Instrument]
    intervals: list[str]
    warmup_count: int = Field(default=200, gt=0)


class CandleRegistry(AbstractRegistry):
    """
    Aggregates TickEvents into OHLCV candles.

    Returns a CandleEvent when a bar closes, None while the bar is still building.
    Emits warm-up candles during setup() by fetching historical data from the broker.
    """

    def __init__(
        self,
        config: CandleConfig,
        broker: Broker,
        candle: AbstractCandleDataStore,
        audit: AbstractAuditStore,
    ) -> None:
        self._config = config
        self._broker = broker
        self._candle = candle
        self._audit = audit

        self._symbols: list[_SymbolConfig] = [
            _SymbolConfig(
                symbol=inst.symbol,
                instrument_token=inst.token,
                instrument_type=InstrumentType(inst.instrument_type),
            )
            for inst in config.instruments
        ]
        self._token_sc: dict[int, _SymbolConfig] = {sc.instrument_token: sc for sc in self._symbols}
        self._bars: dict[tuple[str, str], PartialBar] = {}

    # ------------------------------------------------------------------
    # Warm-up — call once before the live tick stream starts
    # ------------------------------------------------------------------

    async def warmup(self) -> list[CandleEvent]:
        """Fetch historical candles and return them as CandleEvents (tick_log_id=0)."""
        events: list[CandleEvent] = []
        now = datetime.now(UTC)
        max_minutes = max(
            (_INTERVAL_MINUTES.get(iv, 1) for iv in self._config.intervals), default=1
        )
        # Convert trading-time lookback to calendar time: account for non-trading
        # hours and weekends so we always fetch enough historical bars.
        trading_minutes_needed = self._config.warmup_count * max_minutes
        calendar_minutes = trading_minutes_needed * _CALENDAR_MINUTES_PER_TRADING_MINUTE
        lookback_hours = int(calendar_minutes / 60) + 24  # +24h buffer for holidays
        start = now - timedelta(hours=lookback_hours)

        for sc in self._symbols:
            for interval in self._config.intervals:
                try:
                    df = self._broker.get_ohlc(sc.symbol, interval, start, now)
                except Exception as exc:
                    logger.warning(
                        "CandleRegistry: warmup failed for %s %s — %s", sc.symbol, interval, exc
                    )
                    continue
                if df.is_empty():
                    continue
                warmup_rows: list[CandleRow] = []
                for row in df.tail(self._config.warmup_count).iter_rows(named=True):
                    try:
                        ts = _ensure_utc(row["date"])
                        events.append(
                            CandleEvent(
                                symbol=sc.symbol,
                                instrument_type=sc.instrument_type,
                                interval=interval,
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=int(row.get("volume", 0)),
                                timestamp=ts,
                                tick_log_id=0,
                            )
                        )
                        warmup_rows.append(
                            CandleRow(
                                symbol=sc.symbol,
                                interval=interval,
                                ts=ts,
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=int(row.get("volume", 0)),
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "CandleRegistry: invalid warmup row %s %s — %s",
                            sc.symbol,
                            interval,
                            exc,
                        )
                if warmup_rows:
                    try:
                        await self._candle.save_candles(warmup_rows)
                    except Exception as exc:
                        logger.warning(
                            "CandleRegistry: warmup candle persist failed for %s %s — %s",
                            sc.symbol,
                            interval,
                            exc,
                        )
        logger.info("CandleRegistry: warmup produced %d candles", len(events))
        return events

    # ------------------------------------------------------------------
    # AbstractRegistry
    # ------------------------------------------------------------------

    async def handle(self, tick: TickEvent) -> CandleEvent | None:  # type: ignore[override]
        """
        Update the partial bar for this tick's instrument.

        Returns a CandleEvent if a bar just closed, None otherwise.
        """
        sc = self._token_sc.get(tick.instrument_token)
        if sc is None:
            return None

        for interval in self._config.intervals:
            result = await self._process_tick(sc, interval, tick)
            if result is not None:
                fire(self._log_candle(result))
                return result

        return None

    async def _process_tick(
        self, sc: _SymbolConfig, interval: str, tick: TickEvent
    ) -> CandleEvent | None:
        key = (sc.symbol, interval)
        bar_open = _bar_open_time(tick.timestamp, interval)
        existing = self._bars.get(key)

        if existing is None:
            self._bars[key] = _new_bar(sc, interval, tick, bar_open)
            return None

        if bar_open > existing.bar_open_time:
            existing.tick_log_id = tick.tick_log_id
            candle = self._close_bar(existing)
            self._bars[key] = _new_bar(sc, interval, tick, bar_open)
            return candle

        existing.high = max(existing.high, tick.last_price)
        existing.low = min(existing.low, tick.last_price)
        existing.close = tick.last_price
        existing.volume += tick.volume
        existing.tick_log_id = tick.tick_log_id
        return None

    def _close_bar(self, bar: PartialBar) -> CandleEvent:
        minutes = _INTERVAL_MINUTES.get(bar.interval, 1)
        bar_close = bar.bar_open_time + timedelta(minutes=minutes)
        return CandleEvent(
            symbol=bar.symbol,
            instrument_type=bar.instrument_type,
            interval=bar.interval,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            timestamp=bar_close,
            tick_log_id=bar.tick_log_id,
        )

    async def _log_candle(self, event: CandleEvent) -> None:
        try:
            await self._candle.save_candles(
                [
                    {
                        "symbol": event.symbol,
                        "interval": event.interval,
                        "ts": event.timestamp,
                        "open": event.open,
                        "high": event.high,
                        "low": event.low,
                        "close": event.close,
                        "volume": event.volume,
                    }
                ]
            )
            if event.tick_log_id > 0:
                await self._audit.log_decision(
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
        except Exception as exc:
            logger.error(
                "CandleRegistry: candle persist/log failed for %s %s — %s: %s",
                event.symbol,
                event.interval,
                type(exc).__name__,
                exc,
            )
