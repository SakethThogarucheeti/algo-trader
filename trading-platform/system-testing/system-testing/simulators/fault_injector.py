from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from trading.core.messaging import MessageBus

logger = logging.getLogger(__name__)


class FaultInjector:
    """
    Injects network-level faults into a ``MessageBus`` for testing resilience.

    Monkey-patches ``bus.publish`` in the ``async with`` block and restores
    the original on exit.

    Fault types (configurable per channel)
    ---------------------------------------
    - Drop: message is silently discarded with probability ``rate``.
    - Delay: message is delayed by a random amount in ``[min_secs, max_secs]``.
    - Duplicate: message is published twice with probability ``rate``.

    Multiple fault types can be applied to the same channel; they compose:
    drop is evaluated first, then delay, then duplicate.

    Reproducibility
    ---------------
    Pass ``seed`` to fix the RNG for deterministic fault sequences.

    Usage::

        fi = (
            FaultInjector(bus, seed=42)
            .with_drop_rate("signals:algo1", rate=0.1)
            .with_delay("fills", min_secs=0.01, max_secs=0.05)
        )
        async with fi:
            await runtime.start()
    """

    def __init__(self, bus: MessageBus, seed: int | None = None) -> None:
        self._bus = bus
        self._rng = random.Random(seed)
        self._drop_rates: dict[str, float] = {}
        self._delays: dict[str, tuple[float, float]] = {}
        self._dup_rates: dict[str, float] = {}
        self._original_publish: Callable[..., Awaitable[None]] | None = None

    def with_drop_rate(self, channel: str, rate: float) -> FaultInjector:
        """Drop messages on *channel* with probability *rate* (0.0–1.0)."""
        self._drop_rates[channel] = rate
        return self

    def with_delay(self, channel: str, min_secs: float, max_secs: float) -> FaultInjector:
        """Delay messages on *channel* by a random amount in [min_secs, max_secs]."""
        self._delays[channel] = (min_secs, max_secs)
        return self

    def with_duplicate_rate(self, channel: str, rate: float) -> FaultInjector:
        """Duplicate messages on *channel* with probability *rate* (0.0–1.0)."""
        self._dup_rates[channel] = rate
        return self

    async def __aenter__(self) -> FaultInjector:
        self._original_publish = self._bus.publish  # type: ignore[method-assign]
        self._bus.publish = self._faulty_publish  # type: ignore[method-assign]
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._original_publish is not None:
            self._bus.publish = self._original_publish  # type: ignore[method-assign]
            self._original_publish = None

    async def _faulty_publish(self, channel: str, event: BaseModel) -> None:
        assert self._original_publish is not None

        # 1. Drop check
        drop_rate = self._drop_rates.get(channel, 0.0)
        if drop_rate > 0 and self._rng.random() < drop_rate:
            logger.debug("FaultInjector: DROP channel=%r event=%r", channel, event)
            return

        # 2. Delay check
        delay = self._delays.get(channel)
        if delay is not None:
            secs = self._rng.uniform(*delay)
            await asyncio.sleep(secs)

        # 3. Publish
        await self._original_publish(channel, event)
        logger.debug("FaultInjector: PUBLISH channel=%r", channel)

        # 4. Duplicate check
        dup_rate = self._dup_rates.get(channel, 0.0)
        if dup_rate > 0 and self._rng.random() < dup_rate:
            logger.debug("FaultInjector: DUPLICATE channel=%r", channel)
            await self._original_publish(channel, event)
