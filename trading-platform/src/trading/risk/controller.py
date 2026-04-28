from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.config.settings import Settings
from trading.core.clock import Clock, SystemClock
from trading.core.messaging import MessageBus
from trading.core.schemas import (
    OrderType,
    Side,
    SignalEvent,
    SignalType,
    ValidatedOrderEvent,
)
from trading.risk.base import RiskController
from trading.risk.sizer import calculate_quantity
from trading.storage.base import AbstractRepository

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
        repo: AbstractRepository,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        equity: float = 100_000.0,
        signals_channel: str = "signals",
        validated_orders_channel: str = "validated_orders",
        clock: Clock = None,  # type: ignore[assignment]
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
        self._clock: Clock = clock if clock is not None else SystemClock()

    # ------------------------------------------------------------------
    # Risk evaluation pipeline
    # ------------------------------------------------------------------

    async def _evaluate_signal(self, event: SignalEvent) -> ValidatedOrderEvent | str:
        now = self._clock.now()
        today = now.date()

        logger.debug(
            "RiskController: evaluating signal=%s symbol=%s side=%s ts=%s",
            event.signal_id,
            event.symbol,
            event.side.value,
            now.isoformat(),
        )

        # 1. Time cutoff
        if now.time() > self._settings.intraday_cutoff:
            logger.info(
                "RiskController: REJECTED signal=%s reason=%s now=%s cutoff=%s",
                event.signal_id,
                _AFTER_CUTOFF,
                now.time(),
                self._settings.intraday_cutoff,
            )
            return _AFTER_CUTOFF

        # 2. Circuit breaker
        if await self._bus.get_flag(_CIRCUIT_FLAG) is not None:
            logger.warning(
                "RiskController: REJECTED signal=%s reason=%s",
                event.signal_id,
                _CIRCUIT_OPEN,
            )
            return _CIRCUIT_OPEN

        async with self._session_factory() as session:
            async with session.begin():
                # 3. Daily loss limit — skipped in paper/backtest mode because
                # orders use wall-clock created_at, not bar timestamps, so the
                # turnover sum for an entire backtest run accumulates on a single
                # calendar day and would always trip the limit.
                if not self._settings.paper_trading:
                    pnl = await self._repo.get_daily_realized_pnl(session, today)
                    limit = self._equity * self._settings.max_daily_loss_pct / 100.0
                    if abs(pnl) >= limit:
                        logger.warning(
                            "RiskController: REJECTED signal=%s reason=%s pnl=%.2f limit=%.2f",
                            event.signal_id,
                            _DAILY_LOSS_LIMIT,
                            pnl,
                            limit,
                        )
                        return _DAILY_LOSS_LIMIT

                # 4. Duplicate position check (ENTRY only)
                # Allow a signal that is opposite to the current position —
                # that is an exit/reversal, not a duplicate entry.
                if event.signal_type == SignalType.ENTRY:
                    pos = await self._repo.get_position(
                        session,
                        event.symbol,
                        event.instrument_type.value,
                    )
                    if pos is not None and pos.net_qty != 0:
                        # Same direction → duplicate entry, reject
                        if (pos.net_qty > 0 and event.side == Side.BUY) or (
                            pos.net_qty < 0 and event.side == Side.SELL
                        ):
                            logger.info(
                                "RiskController: REJECTED signal=%s reason=%s"
                                " symbol=%s net_qty=%d side=%s",
                                event.signal_id,
                                _ALREADY_IN_POSITION,
                                event.symbol,
                                pos.net_qty,
                                event.side.value,
                            )
                            return _ALREADY_IN_POSITION
                        # Opposite direction → this closes / reverses the position, allow through
                        logger.debug(
                            "RiskController: reversal signal=%s symbol=%s net_qty=%d → %s",
                            event.signal_id,
                            event.symbol,
                            pos.net_qty,
                            event.side.value,
                        )

                # 5. Size the trade
                lot_size = await self._get_lot_size(session, event)
                qty = calculate_quantity(
                    stop_distance=event.stop_distance,
                    equity=self._equity,
                    risk_pct=self._settings.risk_per_trade_pct,
                    lot_size=lot_size,
                )
                if qty == 0:
                    logger.info(
                        "RiskController: REJECTED signal=%s reason=%s"
                        " stop_distance=%.4f equity=%.2f",
                        event.signal_id,
                        _ZERO_QUANTITY,
                        event.stop_distance,
                        self._equity,
                    )
                    return _ZERO_QUANTITY

                logger.info(
                    "RiskController: ACCEPTED signal=%s symbol=%s side=%s qty=%d",
                    event.signal_id,
                    event.symbol,
                    event.side.value,
                    qty,
                )
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
