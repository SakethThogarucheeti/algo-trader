from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MessageBus:
    """
    Thin async wrapper over Redis pub/sub.

    All inter-module communication goes through here — no module ever
    calls redis directly. This keeps the Redis dependency behind a
    single seam that is easy to replace in tests (fakeredis).

    Publishing
    ----------
    Serialises a Pydantic model to JSON and publishes it to a channel.

    Subscribing
    -----------
    Spawns an asyncio Task that reads messages from a channel, deserialises
    them into the given Pydantic model, and calls the handler. Invalid
    messages are logged and skipped — the loop never crashes on bad data.

    Flags
    -----
    Thin SET/GET wrappers used for circuit-breaker flags.
    """

    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._tasks: list[asyncio.Task[None]] = []

    async def publish(self, channel: str, event: BaseModel) -> None:
        """Serialise *event* to JSON and publish it on *channel*."""
        await self._redis.publish(channel, event.model_dump_json())

    def subscribe(
        self,
        channel: str,
        model: type[T],
        handler: Callable[[T], Awaitable[None]],
    ) -> asyncio.Task[None]:
        """
        Subscribe to *channel* and call *handler* with each validated message.

        Returns the background asyncio.Task. The caller does not need to await
        it — the task runs until cancelled (e.g. when the component stops).
        """
        task = asyncio.get_event_loop().create_task(
            self._listen(channel, model, handler),
            name=f"subscribe:{channel}",
        )
        self._tasks.append(task)
        return task

    async def _listen(
        self,
        channel: str,
        model: type[T],
        handler: Callable[[T], Awaitable[None]],
    ) -> None:
        async with self._redis.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                data: Any = raw["data"]
                try:
                    event = model.model_validate_json(data)
                except (ValidationError, ValueError) as exc:
                    logger.warning(
                        "MessageBus: invalid message on channel %r — %s",
                        channel,
                        exc,
                    )
                    continue
                try:
                    await handler(event)
                except Exception:
                    logger.exception(
                        "MessageBus: handler raised on channel %r — "
                        "message skipped, loop continues. "
                        "Raw payload: %.200s",
                        channel,
                        data,
                    )

    async def set_flag(
        self,
        key: str,
        value: str,
        ex: int | None = None,
    ) -> None:
        """SET a Redis key, optionally with an expiry in seconds."""
        await self._redis.set(key, value, ex=ex)

    async def get_flag(self, key: str) -> str | None:
        """GET a Redis key, returning None if absent."""
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    async def delete_flag(self, key: str) -> None:
        """DELETE a Redis key."""
        await self._redis.delete(key)

    async def close(self) -> None:
        """Cancel all subscription tasks and close the Redis connection."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._redis.aclose()
