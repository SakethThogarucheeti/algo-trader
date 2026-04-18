from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.config.settings import Settings
from trading.core.messaging import MessageBus
from trading.core.schemas import (
    OrderType,
    SignalEvent,
    SignalType,
    ValidatedOrderEvent,
)
from trading.risk.base import RiskController
from trading.risk.sizer import calculate_quantity
from trading.storage.repository import Repository

logger = logging.getLogger(__name__)

# Rejection reason codes (written to audit_logs and decision_logs)
_AFTER_CUTOFF = "AFTER_CUTOFF"
_CIRCUIT_OPEN = "CIRCUIT_OPEN"
_DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
_ALREADY_IN_POSITION = "ALREADY_IN_POSITION"
_ZERO_QUANTITY = "ZERO_QUANTITY"

_CIRCUIT_FLAG = "circuit:ingestor:open"


class DefaultRiskController(RiskController):
    """
    Default 5-step risk evaluation pipeline.

    Rejection checks (in order):
    1. Intraday time cutoff
    2. Circuit breaker (ingestor disconnected > 30s)
    3. Daily loss limit exceeded
    4. Duplicate position (ENTRY while already in position)
    5. Zero quantity after sizing

    All rejections are appended to audit_logs and decision_logs.
    Accepted signals become ValidatedOrderEvent and are published to the
    configured ``validated_orders_channel``.
    """

    def __init__(
        self,
        bus: MessageBus,
        repo: Repository,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        equity: float = 100_000.0,
        signals_channel: str = "signals",
        validated_orders_channel: str = "validated_orders",
    ) -> None:
        super().__init__(
            bus=bus,
            repo=repo,
            session_factory=session_factory,
            signals_channel=signals_channel,
            validated_orders_channel=validated_orders_channel,
        )
        self._settings = settings
        self._equity = equity

    # ------------------------------------------------------------------
    # Risk evaluation pipeline
    # ------------------------------------------------------------------

    async def _evaluate_signal(self, event: SignalEvent) -> ValidatedOrderEvent | str:
        now = datetime.now(UTC)
        today = now.date()

        # 1. Time cutoff
        if now.time() > self._settings.intraday_cutoff:
            return _AFTER_CUTOFF

        # 2. Circuit breaker
        if await self._bus.get_flag(_CIRCUIT_FLAG) is not None:
            return _CIRCUIT_OPEN

        async with self._session_factory() as session:
            async with session.begin():
                # 3. Daily loss limit
                pnl = await self._repo.get_daily_realized_pnl(session, today)
                limit = self._equity * self._settings.max_daily_loss_pct / 100.0
                if abs(pnl) >= limit:
                    return _DAILY_LOSS_LIMIT

                # 4. Duplicate position check (ENTRY only)
                if event.signal_type == SignalType.ENTRY:
                    pos = await self._repo.get_position(
                        session,
                        event.symbol,
                        event.instrument_type.value,
                    )
                    if pos is not None and pos.net_qty != 0:
                        return _ALREADY_IN_POSITION

                # 5. Size the trade
                lot_size = await self._get_lot_size(session, event)
                qty = calculate_quantity(
                    stop_distance=event.stop_distance,
                    equity=self._equity,
                    risk_pct=self._settings.risk_per_trade_pct,
                    lot_size=lot_size,
                )
                if qty == 0:
                    return _ZERO_QUANTITY

                await self._repo.log_audit(
                    session,
                    f"risk_controller[{self._signals_channel}]",
                    "INFO",
                    f"signal {event.signal_id} accepted qty={qty}",
                )

        return ValidatedOrderEvent(
            signal_id=event.signal_id,
            symbol=event.symbol,
            instrument_type=event.instrument_type,
            side=event.side,
            quantity=qty,
            order_type=OrderType.MARKET,
            limit_price=None,
            tick_log_id=event.tick_log_id,
        )

    async def _get_lot_size(self, session: AsyncSession, event: SignalEvent) -> int | None:
        """Look up lot size from the instruments table. Returns None for EQUITY."""
        # Instrument token is not on SignalEvent; perform a symbol lookup.
        # Returns None (equity lot sizing) — F&O support populates from DB when
        # instruments table has lot_size wired up.
        return None
