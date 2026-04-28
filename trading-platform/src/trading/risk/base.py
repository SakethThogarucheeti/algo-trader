from __future__ import annotations

import asyncio
import logging
from abc import abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.messaging import MessageBus
from trading.core.schemas import SignalEvent, ValidatedOrderEvent
from trading.engine.component import Component
from trading.storage.base import AbstractRepository

logger = logging.getLogger(__name__)


class RiskController(Component):
    """
    Abstract base for all risk evaluation components.

    Lifecycle
    ---------
    On startup, subscribes to ``signals_channel`` (default ``"signals"``).
    Each incoming ``SignalEvent`` is passed to ``_evaluate_signal()``.
    If accepted, the resulting ``ValidatedOrderEvent`` is published to
    ``validated_orders_channel``. If rejected, the reason is written to
    ``audit_logs`` and a ``SIGNAL_REJECTED`` decision log is emitted.

    Subclasses only need to implement ``_evaluate_signal()`` — all channel
    wiring, audit logging, and decision logging is handled here.

    Bucket / algo scoping
    ---------------------
    Pass ``signals_channel="signals:algo_name"`` and
    ``validated_orders_channel="validated_orders:algo_name"`` to scope
    a controller to a specific algo's channels.
    """

    def __init__(
        self,
        bus: MessageBus,
        repo: AbstractRepository,
        session_factory: async_sessionmaker[AsyncSession],
        signals_channel: str = "signals",
        validated_orders_channel: str = "validated_orders",
    ) -> None:
        super().__init__(name=f"risk_controller[{signals_channel}]")
        self._bus = bus
        self._repo = repo
        self._session_factory = session_factory
        self._signals_channel = signals_channel
        self._validated_orders_channel = validated_orders_channel

    # ------------------------------------------------------------------
    # Component lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        self._bus.subscribe(self._signals_channel, SignalEvent, self._on_signal)
        logger.info(
            "RiskController: subscribed to %s → %s",
            self._signals_channel,
            self._validated_orders_channel,
        )

    async def _run(self) -> None:
        from anyio import sleep_forever

        await sleep_forever()

    # ------------------------------------------------------------------
    # Signal dispatcher — calls subclass evaluate, handles outcome
    # ------------------------------------------------------------------

    async def _on_signal(self, event: SignalEvent) -> None:
        result = await self._evaluate_signal(event)

        if isinstance(result, ValidatedOrderEvent):
            # Persist the Signal row synchronously before publishing so that
            # the executor's Order insert (which has a FK on signals.id) never
            # races with an unpersisted signal.
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        await self._repo.save_signal(session, event)
            except Exception:
                logger.warning(
                    "RiskController: failed to persist signal %s — "
                    "order placement will proceed but audit trail is incomplete",
                    event.signal_id,
                )

            asyncio.get_running_loop().create_task(
                self._log_decision(
                    step="SIGNAL_ACCEPTED",
                    event=event,
                    context={
                        "qty": result.quantity,
                        "order_type": result.order_type.value,
                        "validated_orders_channel": self._validated_orders_channel,
                    },
                )
            )
            await self._bus.publish(self._validated_orders_channel, result)
            logger.info(
                "RiskController[%s]: signal %s accepted → qty=%d",
                self._signals_channel,
                event.signal_id,
                result.quantity,
            )
        else:
            reason: str = result
            asyncio.get_running_loop().create_task(
                self._log_decision(
                    step="SIGNAL_REJECTED",
                    event=event,
                    context={"reason": reason},
                )
            )
            await self._reject(event, reason)

    # ------------------------------------------------------------------
    # Shared helpers available to subclasses
    # ------------------------------------------------------------------

    async def _reject(self, event: SignalEvent, reason: str) -> None:
        logger.info(
            "RiskController[%s]: signal %s rejected — %s",
            self._signals_channel,
            event.signal_id,
            reason,
        )
        async with self._session_factory() as session:
            async with session.begin():
                await self._repo.log_audit(
                    session,
                    f"risk_controller[{self._signals_channel}]",
                    "WARNING",
                    f"signal {event.signal_id} rejected: {reason}",
                )

    async def _log_decision(
        self,
        step: str,
        event: SignalEvent,
        context: dict[str, object],
    ) -> None:
        if event.tick_log_id == 0:
            # Backtest candles use tick_log_id=0; no real tick_logs row exists — skip.
            return
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.log_decision(
                        session,
                        step=step,
                        symbol=event.symbol,
                        tick_log_id=event.tick_log_id,
                        context=context,
                        algo_name=self._signals_channel.removeprefix("signals:") or None,
                        signal_id=event.signal_id,
                    )
        except Exception:
            logger.warning(
                "RiskController: decision log failed for signal %s — audit trail gap",
                event.signal_id,
            )

    # ------------------------------------------------------------------
    # Abstract hook — subclasses implement this
    # ------------------------------------------------------------------

    @abstractmethod
    async def _evaluate_signal(self, event: SignalEvent) -> ValidatedOrderEvent | str:
        """
        Evaluate a signal and decide whether to accept or reject it.

        Returns
        -------
        ValidatedOrderEvent
            The order to place if the signal is accepted.
        str
            A short rejection reason code (e.g. ``"AFTER_CUTOFF"``) if the
            signal should be rejected. Written to audit_logs and decision_logs.
        """
