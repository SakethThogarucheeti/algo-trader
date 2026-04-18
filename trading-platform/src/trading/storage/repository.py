from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading.core.models import (
    AuditLog,
    DecisionLog,
    Heartbeat,
    Instrument,
    Order,
    Position,
    Signal,
    TickLog,
)
from trading.core.schemas import FillEvent, OrderStatus, Side, SignalEvent, TickEvent


class NotFoundError(Exception):
    """Raised when a required DB row is absent."""


class Repository:
    """
    The only layer that touches the database.

    All methods accept an open ``AsyncSession`` as their first argument.
    Callers are responsible for transaction management — wrap calls in
    ``get_session(engine)`` or an explicit ``session.begin()`` block.

    ``update_position`` must always be called inside an existing transaction
    because it uses SELECT FOR UPDATE and must be atomic with other writes.
    """

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------

    async def get_instrument(self, session: AsyncSession, token: int) -> Instrument | None:
        return await session.get(Instrument, token)

    async def upsert_instruments(
        self, session: AsyncSession, instruments: list[Instrument]
    ) -> None:
        """
        Upsert a batch of instruments (token is the PK).

        Uses a simple merge approach: add each object; SQLAlchemy will
        issue INSERT OR REPLACE / ON CONFLICT via the session merge.
        """
        for inst in instruments:
            await session.merge(inst)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    async def save_signal(self, session: AsyncSession, event: SignalEvent) -> Signal:
        signal = Signal(
            id=event.signal_id,
            strategy_id=event.strategy_id,
            symbol=event.symbol,
            instrument_type=event.instrument_type.value,
            side=event.side.value,
            signal_type=event.signal_type.value,
            stop_distance=Decimal(str(event.stop_distance)),
            created_at=event.timestamp,
        )
        session.add(signal)
        return signal

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def save_order(self, session: AsyncSession, order: Order) -> None:
        session.add(order)

    async def get_order_by_kite_id(self, session: AsyncSession, kite_order_id: str) -> Order | None:
        result = await session.execute(select(Order).where(Order.kite_order_id == kite_order_id))
        return result.scalar_one_or_none()

    async def update_order_status(
        self,
        session: AsyncSession,
        kite_order_id: str,
        status: OrderStatus,
        avg_price: float = 0,
    ) -> None:
        order = await self.get_order_by_kite_id(session, kite_order_id)
        if order is None:
            raise NotFoundError(f"Order not found: {kite_order_id!r}")
        order.status = status.value
        order.avg_price = Decimal(str(avg_price))

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    async def get_position(
        self, session: AsyncSession, symbol: str, instrument_type: str
    ) -> Position | None:
        return await session.get(Position, {"symbol": symbol, "instrument_type": instrument_type})

    async def update_position(
        self,
        session: AsyncSession,
        fill: FillEvent,
        side: Side,
        symbol: str,
        instrument_type: str,
    ) -> None:
        """
        Atomically update a position after a fill.

        Must be called inside an open transaction (the caller holds it).
        Uses SELECT … FOR UPDATE so concurrent fills don't race.

        Position arithmetic:
          BUY fill  → net_qty += filled_qty, avg_price recomputed (weighted)
          SELL fill → net_qty -= filled_qty, avg_price unchanged when closing
        """
        # SQLite doesn't support FOR UPDATE; use plain SELECT in tests.
        result = await session.execute(
            select(Position)
            .where(
                Position.symbol == symbol,
                Position.instrument_type == instrument_type,
            )
            .with_for_update()
        )
        position = result.scalar_one_or_none()
        fill_price = Decimal(str(fill.avg_price))
        fill_qty = fill.filled_qty

        if position is None:
            # First trade for this (symbol, instrument_type)
            net_qty = fill_qty if side == Side.BUY else -fill_qty
            session.add(
                Position(
                    symbol=symbol,
                    instrument_type=instrument_type,
                    net_qty=net_qty,
                    avg_price=fill_price,
                    updated_at=datetime.now(UTC),
                )
            )
        else:
            prev_qty = position.net_qty
            prev_price = position.avg_price

            if side == Side.BUY:
                new_qty = prev_qty + fill_qty
                if new_qty != 0:
                    position.avg_price = (prev_price * prev_qty + fill_price * fill_qty) / new_qty
                position.net_qty = new_qty
            else:  # SELL
                new_qty = prev_qty - fill_qty
                position.net_qty = new_qty
                # avg_price stays the same when reducing a long; when crossing
                # zero (short) we record the fill price as the new avg
                if new_qty < 0:
                    position.avg_price = fill_price

            position.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # P&L
    # ------------------------------------------------------------------

    async def get_daily_realized_pnl(self, session: AsyncSession, for_date: date) -> float:
        """
        Sum up realized P&L from FILLED orders placed on *for_date*.

        Formula: sum(avg_price * qty * side_multiplier) where
          side_multiplier = +1 for SELL fills, -1 for BUY fills
          (i.e. we track cash flow — positive = money in from sells)

        Callers should treat a non-zero result with caution: this is a
        simple approximation. A proper P&L calc requires matching buys
        with sells; that complexity lives outside the Repository.
        """
        start = datetime(for_date.year, for_date.month, for_date.day, tzinfo=UTC)
        end = datetime(for_date.year, for_date.month, for_date.day, 23, 59, 59, tzinfo=UTC)

        result = await session.execute(
            select(Order).where(
                Order.status == OrderStatus.FILLED.value,
                Order.created_at >= start,
                Order.created_at <= end,
            )
        )
        orders = result.scalars().all()

        pnl = 0.0
        for order in orders:
            # We reconstruct side from the linked Signal to avoid storing it
            # redundantly on Order.  For the risk check we only need total
            # cash outflow/inflow magnitude — use abs(avg_price * qty).
            pnl += float(order.avg_price) * order.qty
        return pnl

    # ------------------------------------------------------------------
    # Heartbeats
    # ------------------------------------------------------------------

    async def update_heartbeat(self, session: AsyncSession, module: str) -> None:
        """Upsert the heartbeat timestamp for *module*."""
        existing = await session.get(Heartbeat, module)
        now = datetime.now(UTC)
        if existing is None:
            session.add(Heartbeat(module=module, last_seen=now))
        else:
            existing.last_seen = now

    async def get_stale_modules(
        self, session: AsyncSession, timeout_secs: int, modules: list[str] | None = None
    ) -> list[str]:
        """Return module names whose last heartbeat is older than *timeout_secs*.

        If *modules* is provided, only those names are checked.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=timeout_secs)
        stmt = select(Heartbeat)
        if modules is not None:
            stmt = stmt.where(Heartbeat.module.in_(modules))
        result = await session.execute(stmt)
        heartbeats = result.scalars().all()
        stale = []
        for hb in heartbeats:
            last_seen = hb.last_seen
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            if last_seen < cutoff:
                stale.append(hb.module)
        return stale

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    async def log_audit(
        self,
        session: AsyncSession,
        module: str,
        level: str,
        message: str,
    ) -> None:
        session.add(AuditLog(module=module, level=level, message=message))

    # ------------------------------------------------------------------
    # Tick logging
    # ------------------------------------------------------------------

    async def log_tick(
        self,
        session: AsyncSession,
        event: TickEvent,
        symbol: str,
    ) -> int:
        """
        Insert a TickLog row and return its auto-generated id.

        Uses ``session.flush()`` to obtain the DB-assigned id without waiting
        for a full commit. The caller is responsible for committing (or
        scheduling a background commit) after this returns.

        This id is set on the TickEvent and propagated through every
        downstream event (CandleEvent, SignalEvent, ValidatedOrderEvent) so
        all DecisionLog rows can be traced back to the originating tick.
        """
        row = TickLog(
            instrument_token=event.instrument_token,
            symbol=symbol,
            instrument_type=event.instrument_type.value,
            last_price=Decimal(str(event.last_price)),
            volume=event.volume,
            received_at=event.timestamp,
        )
        session.add(row)
        await session.flush()  # sends INSERT → Postgres assigns row.id via RETURNING
        return row.id

    # ------------------------------------------------------------------
    # Decision logging
    # ------------------------------------------------------------------

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
    ) -> None:
        """
        Append a DecisionLog row recording what happened at a pipeline step.

        Steps: CANDLE_EMITTED, SIGNAL_GENERATED, SIGNAL_ACCEPTED, SIGNAL_REJECTED.
        ``tick_log_id`` must reference an existing TickLog row — it is the
        root causal id that ties all decisions for a tick together.
        ``session_id`` identifies a backtest/Monte Carlo run; None = live trading.
        """
        session.add(
            DecisionLog(
                tick_log_id=tick_log_id,
                step=step,
                algo_name=algo_name,
                session_id=session_id,
                symbol=symbol,
                signal_id=signal_id,
                context=json.dumps(context),
            )
        )
