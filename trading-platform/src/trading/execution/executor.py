from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.core.messaging import MessageBus
from trading.core.models import Order
from trading.core.schemas import (
    FillEvent,
    OrderEvent,
    OrderStatus,
    Side,
    ValidatedOrderEvent,
)
from trading.engine.component import Component
from trading.execution.base import ExecutionEngine
from trading.execution.idempotency import is_duplicate
from trading.storage.base import AbstractRepository
from trading.storage.repository import NotFoundError

logger = logging.getLogger(__name__)


class DirectExecutionEngine(ExecutionEngine):
    """
    Concrete execution engine that routes orders directly to the broker.

    Idempotency
    -----------
    Each ``signal_id`` is checked against the orders table before placing.
    If an Order row already exists the event is silently dropped — no broker
    call, no DB write.

    Unit of Work
    ------------
    Order status update + position update run in a single SQLAlchemy
    transaction. A DB failure rolls back both, preventing ghost positions.

    Fill handling
    -------------
    In live trading, Zerodha sends postbacks to a webhook. For paper trading
    the executor simulates an immediate fill at the last known price.
    """

    def __init__(
        self,
        bus: MessageBus,
        broker: Broker,
        repo: AbstractRepository,
        session_factory: async_sessionmaker[AsyncSession],
        paper_price_store: object | None = None,  # PriceStore | None
        orders_channel: str = "orders",
        fills_channel: str = "fills",
        on_order_placed: Callable[[str, str, Side], None] | None = None,
    ) -> None:
        self._bus = bus
        self._broker = broker
        self._repo = repo
        self._session_factory = session_factory
        self._price_store = paper_price_store
        self._orders_channel = orders_channel
        self._fills_channel = fills_channel
        self._on_order_placed = on_order_placed

    async def execute(self, event: ValidatedOrderEvent) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                # 1. Idempotency check
                if await is_duplicate(event.signal_id, session):
                    logger.info(
                        "DirectExecutionEngine: duplicate signal_id %s — dropping",
                        event.signal_id,
                    )
                    return

                # 2. Persist PENDING order before broker call
                order_id = uuid4()
                order = Order(
                    id=order_id,
                    kite_order_id="",  # filled after broker responds
                    signal_id=event.signal_id,
                    status=OrderStatus.PENDING.value,
                    qty=event.quantity,
                    avg_price=Decimal("0"),
                    created_at=datetime.now(UTC),
                )
                await self._repo.save_order(session, order)

        # 3. Call broker outside the transaction (network I/O)
        try:
            kite_order_id = await self._broker.place_order(
                symbol=event.symbol,
                side=event.side,
                qty=event.quantity,
                order_type=event.order_type,
                limit_price=event.limit_price,
            )
            final_status = OrderStatus.PLACED
        except Exception as exc:
            logger.error("DirectExecutionEngine: broker.place_order failed — %s", exc)
            kite_order_id = f"FAILED_{order_id}"
            final_status = OrderStatus.REJECTED

        # 4. Update order with result
        async with self._session_factory() as session:
            async with session.begin():
                order_row = await session.get(Order, order_id)
                if order_row is not None:
                    order_row.kite_order_id = kite_order_id
                    order_row.status = final_status.value

        # 5. Notify fill-tracking callback (synchronous, before bus publish so
        #    the kite_order_id→(symbol, side) mapping is registered before any
        #    FillEvent can arrive on the fills channel).
        if self._on_order_placed is not None:
            self._on_order_placed(kite_order_id, event.symbol, event.side)

        # 6. Publish OrderEvent
        order_event = OrderEvent(
            signal_id=event.signal_id,
            kite_order_id=kite_order_id,
            status=final_status,
            timestamp=datetime.now(UTC),
        )
        await self._bus.publish(self._orders_channel, order_event)
        logger.info(
            "DirectExecutionEngine: order %s status=%s",
            kite_order_id,
            final_status.value,
        )

        # 7. Paper trading: simulate immediate fill at last known price
        if self._price_store is not None and final_status == OrderStatus.PLACED:
            fill_price: float | None = self._price_store.get(event.symbol)  # type: ignore[attr-defined]
            if fill_price is None:
                logger.warning("PaperBroker: no price known for %s — fill skipped", event.symbol)
            else:
                logger.info(
                    "PaperBroker: simulating fill %s @ %.2f x%d",
                    kite_order_id,
                    fill_price,
                    event.quantity,
                )
                await self.handle_fill(
                    kite_order_id=kite_order_id,
                    avg_price=fill_price,
                    filled_qty=event.quantity,
                    symbol=event.symbol,
                    instrument_type=event.instrument_type.value,
                    side=event.side.value,
                )

    async def handle_fill(
        self,
        kite_order_id: str,
        avg_price: float,
        filled_qty: int,
        symbol: str,
        instrument_type: str,
        side: str,
    ) -> None:
        """
        Process a fill notification and update order + position atomically.

        Both the order status update and the position update run in a single
        transaction so a mid-flight DB failure rolls both back cleanly.
        """
        from trading.core.schemas import Side

        fill = FillEvent(
            kite_order_id=kite_order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            timestamp=datetime.now(UTC),
        )

        async with self._session_factory() as session:
            async with session.begin():
                try:
                    await self._repo.update_order_status(
                        session, kite_order_id, OrderStatus.FILLED, avg_price
                    )
                except NotFoundError:
                    logger.warning(
                        "DirectExecutionEngine: fill for unknown order %s — "
                        "possibly a replayed or stale webhook; skipping",
                        kite_order_id,
                    )
                    return
                await self._repo.update_position(
                    session,
                    fill,
                    Side(side),
                    symbol,
                    instrument_type,
                )

        fill_event = FillEvent(
            kite_order_id=kite_order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            timestamp=datetime.now(UTC),
        )
        await self._bus.publish(self._fills_channel, fill_event)
        logger.info(
            "DirectExecutionEngine: fill %s avg=%.2f qty=%d",
            kite_order_id,
            avg_price,
            filled_qty,
        )


class OrderExecutor(Component):
    """
    Lifecycle component that routes validated orders to an ExecutionEngine.

    Subscribes to a validated_orders Redis channel (scoped per algo) and
    delegates all execution logic to the injected ``ExecutionEngine``.
    This separation lets different algos use different execution strategies
    (direct market orders, TWAP, paper simulation, etc.) without changing
    the Component lifecycle code.
    """

    def __init__(
        self,
        bus: MessageBus,
        execution_engine: ExecutionEngine,
        channel: str = "validated_orders",
    ) -> None:
        super().__init__(name=f"order_executor[{channel}]")
        self._bus = bus
        self._engine = execution_engine
        self._channel = channel

    async def _setup(self) -> None:
        self._bus.subscribe(self._channel, ValidatedOrderEvent, self._engine.execute)
        logger.info("OrderExecutor: subscribed to %s channel", self._channel)

    async def _run(self) -> None:
        from anyio import sleep_forever

        await sleep_forever()

    def handle_fill(
        self,
        kite_order_id: str,
        avg_price: float,
        filled_qty: int,
        symbol: str,
        instrument_type: str,
        side: str,
    ):  # type: ignore[return]  # returns a coroutine, caller must await
        """Delegate fill handling to the underlying execution engine."""
        return self._engine.handle_fill(
            kite_order_id=kite_order_id,
            avg_price=avg_price,
            filled_qty=filled_qty,
            symbol=symbol,
            instrument_type=instrument_type,
            side=side,
        )
