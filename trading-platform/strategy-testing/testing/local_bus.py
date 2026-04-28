"""
In-process message bus for backtesting.

Replaces the Redis-backed ``RedisMessageBus`` with a zero-overhead local
implementation. Handlers are called directly (no serialization, no network
round-trips, no polling loops) so backtests run orders of magnitude faster.

The interface is intentionally identical to ``MessageBus`` so that
``BacktestSession`` and all components need no changes.

``set_flag`` / ``get_flag`` / ``delete_flag`` are also implemented in-memory
so the risk controller's circuit-breaker flag checks work correctly.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

from trading.core.messaging import MessageBus

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LocalMessageBus(MessageBus):
    """
    In-process pub/sub bus — used in backtesting.

    ``publish`` delivers a message directly to every handler registered on
    *channel*.  ``subscribe`` registers a handler immediately (no background
    tasks, no network).  There is no serialization overhead — the original
    Pydantic object is passed straight to the handler.
    """

    def __init__(self) -> None:
        # channel → list of (model_type, handler)
        self._handlers: dict[str, list[tuple[type[BaseModel], Callable[..., Awaitable[None]]]]] = {}
        # in-memory flag store (replaces Redis SET/GET for circuit breakers)
        self._flags: dict[str, str] = {}

    async def publish(self, channel: str, event: BaseModel) -> None:
        """Deliver *event* to every handler subscribed to *channel*."""
        for model_cls, handler in self._handlers.get(channel, []):
            if not isinstance(event, model_cls):
                continue
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "LocalMessageBus: handler raised on channel %r — skipping",
                    channel,
                )

    def subscribe(
        self,
        channel: str,
        model: type[T],
        handler: Callable[[T], Awaitable[None]],
    ) -> asyncio.Task[None]:
        """
        Register *handler* for messages of type *model* on *channel*.

        Returns a dummy no-op Task so callers that store the return value
        don't need to be changed.
        """
        self._handlers.setdefault(channel, []).append((model, handler))  # type: ignore[arg-type]

        async def _noop() -> None:
            pass

        loop = asyncio.get_event_loop()
        return loop.create_task(_noop(), name=f"subscribe:{channel}")

    async def set_flag(self, key: str, value: str, ex: int | None = None) -> None:
        self._flags[key] = value

    async def get_flag(self, key: str) -> str | None:
        return self._flags.get(key)

    async def delete_flag(self, key: str) -> None:
        self._flags.pop(key, None)

    async def close(self) -> None:
        """No-op — nothing to clean up."""
        self._handlers.clear()
        self._flags.clear()
