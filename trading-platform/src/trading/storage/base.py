"""Abstract repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from trading.core.models import Instrument, Order, Position
from trading.core.schemas import FillEvent, OrderStatus, Side, SignalEvent, TickEvent


class AbstractRepository(ABC):
    """
    Abstract data-access interface.

    All methods accept an open ``AsyncSession`` as their first argument.
    Callers are responsible for transaction management.

    Concrete implementations decide the backing store — production uses
    SQLAlchemy / Postgres; tests can swap in an in-memory stub.
    """

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    @abstractmethod
    async def save_candles(
        self,
        session: AsyncSession,
        rows: list[dict],
    ) -> None:
        """
        Bulk-insert candle rows. Keys per dict: symbol, interval, ts, open,
        high, low, close, volume. Ignores conflicts on (symbol, interval, ts)
        so repeated calls are idempotent.
        """

    @abstractmethod
    async def get_candles(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str,
        limit: int,
    ) -> list[dict]:
        """
        Return the last *limit* candles for (symbol, interval), ordered
        ts ASC (oldest first, newest last). Each dict has the same keys
        as the rows accepted by save_candles.
        """

    @abstractmethod
    async def get_candles_since(
        self,
        session: AsyncSession,
        symbol: str,
        interval: str,
        since: datetime,
    ) -> list[dict]:
        """
        Return all candles for (symbol, interval) with ts >= *since*,
        ordered ts ASC. Used by session-VWAP which needs bars from the
        current trading-day open onward.
        """

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_instrument(self, session: AsyncSession, token: int) -> Instrument | None: ...

    @abstractmethod
    async def upsert_instruments(
        self, session: AsyncSession, instruments: list[Instrument]
    ) -> None: ...

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    @abstractmethod
    async def save_signal(self, session: AsyncSession, event: SignalEvent) -> object: ...

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    @abstractmethod
    async def save_order(self, session: AsyncSession, order: Order) -> None: ...

    @abstractmethod
    async def get_order_by_kite_id(
        self, session: AsyncSession, kite_order_id: str
    ) -> Order | None: ...

    @abstractmethod
    async def update_order_status(
        self,
        session: AsyncSession,
        kite_order_id: str,
        status: OrderStatus,
        avg_price: float = 0,
    ) -> None: ...

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_position(
        self, session: AsyncSession, symbol: str, instrument_type: str
    ) -> Position | None: ...

    @abstractmethod
    async def update_position(
        self,
        session: AsyncSession,
        fill: FillEvent,
        side: Side,
        symbol: str,
        instrument_type: str,
    ) -> None: ...

    # ------------------------------------------------------------------
    # P&L
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_daily_realized_pnl(self, session: AsyncSession, for_date: date) -> float: ...

    # ------------------------------------------------------------------
    # Heartbeats
    # ------------------------------------------------------------------

    @abstractmethod
    async def update_heartbeat(self, session: AsyncSession, module: str) -> None: ...

    @abstractmethod
    async def get_stale_modules(
        self,
        session: AsyncSession,
        timeout_secs: int,
        modules: list[str] | None = None,
    ) -> list[str]: ...

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    @abstractmethod
    async def log_audit(
        self, session: AsyncSession, module: str, level: str, message: str
    ) -> None: ...

    # ------------------------------------------------------------------
    # Tick logging
    # ------------------------------------------------------------------

    @abstractmethod
    async def log_tick(
        self,
        session: AsyncSession,
        event: TickEvent,
        symbol: str,
    ) -> int: ...

    # ------------------------------------------------------------------
    # Algo config and state
    # ------------------------------------------------------------------

    @abstractmethod
    async def seed_algo_config(
        self,
        session: AsyncSession,
        name: str,
        strategy_id: str,
        warmup_candles: int,
        candle_intervals: list[str],
        equity: float,
        params: dict[str, object],
    ) -> None:
        """Insert algo config if it doesn't exist; never overwrites existing rows."""

    @abstractmethod
    async def upsert_algo_state(
        self,
        session: AsyncSession,
        name: str,
        state: dict[str, object],
    ) -> None:
        """Write (insert or update) the algo state JSON blob."""

    @abstractmethod
    async def get_algo_configs_with_state(
        self, session: AsyncSession
    ) -> list[dict[str, object]]:
        """Return all algo configs joined with their current state."""

    # ------------------------------------------------------------------
    # Decision logging
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Indicator charting
    # ------------------------------------------------------------------

    @abstractmethod
    async def log_indicator(
        self,
        session: AsyncSession,
        algo_name: str,
        symbol: str,
        interval: str,
        chart: str,
        series: str,
        ts: datetime,
        value: float,
        session_id: str | None = None,
    ) -> None:
        """Record one indicator data point for a strategy chart series."""

    @abstractmethod
    async def get_chart_names(
        self,
        session: AsyncSession,
        algo_name: str,
        since: datetime,
        session_id: str | None = None,
    ) -> list[str]:
        """Return distinct chart names that have data for *algo_name* since *since*."""

    @abstractmethod
    async def get_indicator_series(
        self,
        session: AsyncSession,
        algo_name: str,
        chart: str,
        since: datetime,
        session_id: str | None = None,
        limit: int = 500,
    ) -> dict[str, list[dict]]:
        """
        Return all series for *chart* as {series_name: [{"ts": iso_str, "value": float}, ...]}.
        Points are ordered ts ASC, capped at *limit*.
        """

    @abstractmethod
    async def log_decision(
        self,
        session: AsyncSession,
        step: str,
        symbol: str,
        tick_log_id: int,
        context: dict[str, object],
        algo_name: str | None = None,
        signal_id: UUID | None = None,
        session_id: str | None = None,
    ) -> None: ...
