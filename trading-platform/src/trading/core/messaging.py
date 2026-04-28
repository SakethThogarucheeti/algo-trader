from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class Registry:
    """
    In-process event dispatch registry.

    Components register async handlers by name during _setup(), then call
    dispatch() to invoke all handlers registered under that name.

    This replaces Redis pub/sub: events are delivered as direct awaited
    coroutine calls instead of serialised messages over a network channel.
    Multiple handlers can be registered under the same name (fan-out).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}

    def register(self, name: str, handler: Callable[..., Awaitable[None]]) -> None:
        """Register *handler* to be called when *name* is dispatched."""
        self._handlers.setdefault(name, []).append(handler)

    async def dispatch(self, name: str, event: Any) -> None:
        """Call every handler registered under *name* with *event*."""
        for handler in self._handlers.get(name, []):
            try:
                await handler(event)
            except Exception:
                logger.exception("Registry: handler raised for %r — continuing", name)


class FlagStore:
    """
    In-memory key/value store for circuit-breaker flags.

    Replaces the Redis SET/GET/DEL calls previously on MessageBus.
    """

    def __init__(self) -> None:
        self._flags: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self._flags[key] = value

    def get(self, key: str) -> str | None:
        return self._flags.get(key)

    def delete(self, key: str) -> None:
        self._flags.pop(key, None)
