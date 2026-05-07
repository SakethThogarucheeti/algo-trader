from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.broker.paper_broker import AbstractPriceStore
from trading.core.messaging import AbstractRegistry
from trading.core.models import Order
from trading.core.schemas import (
    FillEvent,
    OrderStatus,
    Side,
    ValidatedOrderEvent,
)
from trading.execution.idempotency import is_duplicate
from trading.storage.base import AbstractRepository
from trading.storage.repository import NotFoundError

logger = logging.getLogger(__name__)


class ExecConfig(BaseModel):
    """Configuration for the execution stage."""

    exec_id: str = "direct"  # "paper" | "direct"


class ExecRegistry(AbstractRegistry):
    """
    Routes a ValidatedOrderEvent to the broker and handles fills.

    exec_id="paper"  — simulates an immediate fill at the last known price
    exec_id="direct" — places a real order via the broker

    handle() always returns None (fire-and-forget terminal stage).
    """

    def __init__(
        self,
        config: ExecConfig,
        broker: Broker,
        session_factory: async_sessionmaker[AsyncSession],
        repo: AbstractRepository,
        price_store: AbstractPriceStore | None = None,
    ) -> None:
        self._config = config
        self._broker = broker
        self._session_factory = session_factory
        self._repo = repo
        self._price_store = price_store if config.exec_id == "paper" else None

    # ------------------------------------------------------------------
    # AbstractRegistry
    # ------------------------------------------------------------------

    async def handle(self, event: ValidatedOrderEvent) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                if await is_duplicate(event.signal_id, session):
                    logger.info("ExecRegistry: duplicate signal_id %s — dropping", event.signal_id)
                    return

                order_id = uuid4()
                order = Order(
                    id=order_id,
                    kite_order_id="",
                    signal_id=event.signal_id,
                    status=OrderStatus.PENDING.value,
                    qty=event.quantity,
                    avg_price=Decimal("0"),
                    created_at=datetime.now(UTC),
                )
                await self._repo.save_order(session, order)

        # Broker call outside transaction
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
            logger.error("ExecRegistry: broker.place_order failed — %s", exc)
            kite_order_id = f"FAILED_{order_id}"
            final_status = OrderStatus.REJECTED

        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(Order, order_id)
                if row is not None:
                    row.kite_order_id = kite_order_id
                    row.status = final_status.value

        logger.info("ExecRegistry: order %s status=%s", kite_order_id, final_status.value)

        # Paper trading: simulate immediate fill
        if self._price_store is not None and final_status == OrderStatus.PLACED:
            fill_price: float | None = self._price_store.get(event.symbol)  # type: ignore[attr-defined]
            if fill_price is None:
                logger.warning("ExecRegistry: no price known for %s — fill skipped", event.symbol)
            else:
                await self._handle_fill(
                    kite_order_id=kite_order_id,
                    avg_price=fill_price,
                    filled_qty=event.quantity,
                    symbol=event.symbol,
                    instrument_type=event.instrument_type.value,
                    side=event.side.value,
                )

    async def _handle_fill(
        self,
        kite_order_id: str,
        avg_price: float,
        filled_qty: int,
        symbol: str,
        instrument_type: str,
        side: str,
    ) -> None:
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
                        "ExecRegistry: fill for unknown order %s — skipping", kite_order_id
                    )
                    return
                await self._repo.update_position(
                    session, fill, Side(side), symbol, instrument_type
                )
        logger.info("ExecRegistry: fill %s avg=%.2f qty=%d", kite_order_id, avg_price, filled_qty)
