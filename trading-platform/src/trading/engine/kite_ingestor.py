from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Coroutine
from typing import Any

from anyio import sleep_forever

from trading.broker.base.broker_stream import BrokerStream
from trading.broker.paper_broker import AbstractPriceStore
from trading.broker.types import Tick
from trading.core.context import thread_id
from trading.core.schemas import TickEvent
from trading.engine.component import Component
from trading.registry.tick import TickRegistry

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECS = 30.0

# Downstream callback: receives a TickEvent and returns nothing (or None).
OnTickCallback = Callable[[TickEvent], Coroutine[Any, Any, None]]


class KiteIngestor(Component):
    """
    Maintains the broker WebSocket connection and feeds raw ticks into TickRegistry.

    After TickRegistry validates and persists the tick, each registered
    ``on_tick`` callback is called in order. Register the candle→algo→risk→exec
    chain via ``add_on_tick(callback)`` before starting.

    Lifecycle
    ---------
    _setup:   register WS callbacks → connect → wait for on_connect → subscribe tokens
    _run:     sleep_forever (ticks arrive via callbacks)
    _teardown: cancel circuit timer → close stream
    """

    def __init__(
        self,
        stream: BrokerStream,
        tick_registry: TickRegistry,
        price_store: AbstractPriceStore | None = None,
        connect_timeout_secs: float = _CONNECT_TIMEOUT_SECS,
    ) -> None:
        super().__init__(name="kite_ingestor")
        self._stream = stream
        self._tick_registry = tick_registry
        self._price_store = price_store
        self._connect_timeout_secs = connect_timeout_secs
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected: asyncio.Event | None = None
        self._on_tick_callbacks: list[OnTickCallback] = []

    def add_on_tick(self, callback: OnTickCallback) -> None:
        """Register a downstream callback invoked for every validated tick."""
        self._on_tick_callbacks.append(callback)

    async def _setup(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._connected = asyncio.Event()

        self._stream.set_on_connect(self._on_ws_connect)
        self._stream.set_on_ticks(self._on_ws_ticks)
        self._stream.set_on_disconnect(self._on_ws_disconnect)

        await self._stream.connect()
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=self._connect_timeout_secs)
        except TimeoutError as err:
            raise RuntimeError(
                f"KiteIngestor: WebSocket did not connect within {self._connect_timeout_secs}s"
            ) from err

        tokens = self._tick_registry.get_tokens()
        if tokens:
            await self._stream.subscribe(tokens)
            logger.info("KiteIngestor: connected and subscribed to %d tokens", len(tokens))
        else:
            logger.warning("KiteIngestor: no instruments configured")

    async def _run(self) -> None:
        await sleep_forever()

    async def _teardown(self) -> None:
        self._tick_registry.cancel_circuit_task()
        await self._stream.close()

    # ------------------------------------------------------------------
    # WebSocket thread callbacks
    # ------------------------------------------------------------------

    def _on_ws_connect(self) -> None:
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._on_connected)

    def _on_connected(self) -> None:
        if self._connected is not None:
            self._connected.set()
        self._tick_registry.on_connected()

    def _on_ws_ticks(self, ticks: list[Tick]) -> None:
        if self._loop is None:
            return
        for tick in ticks:
            asyncio.run_coroutine_threadsafe(self._handle_tick(tick), self._loop)

    def _on_ws_disconnect(self, code: int, reason: str) -> None:
        logger.warning("KiteIngestor: disconnected code=%s reason=%r", code, reason)
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._tick_registry.on_disconnected)

    async def _handle_tick(self, raw: Tick) -> None:
        thread_id.set(os.urandom(4).hex())

        tick = await self._tick_registry.handle(raw)
        if tick is None:
            return

        # Keep price store current for paper trading fill simulation
        if self._price_store is not None:
            symbol = self._tick_registry.get_symbol(tick.instrument_token) or ""
            if symbol:
                self._price_store.update(symbol, tick.last_price)  # type: ignore[attr-defined]

        for callback in self._on_tick_callbacks:
            try:
                await callback(tick)
            except Exception:
                logger.exception("KiteIngestor: on_tick callback error")
