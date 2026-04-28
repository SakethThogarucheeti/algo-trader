from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from kiteconnect import KiteTicker  # type: ignore[import-untyped]

from trading.broker.base.broker_stream import BrokerStream
from trading.broker.zerodha.kite_client import KiteClient

logger = logging.getLogger(__name__)


class ZerodhaStream(BrokerStream):
    """
    Thin async wrapper around KiteTicker (WebSocket feed).

    KiteTicker runs in its own background thread; all callbacks arrive
    on that thread. The caller (KiteIngestor) is responsible for bridging
    callbacks to the asyncio event loop.
    """

    def __init__(self, client: KiteClient) -> None:
        self._client = client
        self._ticker: KiteTicker | None = None
        self._on_connect_cb: Callable[[], None] | None = None
        self._on_ticks_cb: Callable[[list[dict]], None] | None = None
        self._on_disconnect_cb: Callable[[int, str], None] | None = None

    def set_on_connect(self, callback: Callable[[], None]) -> None:
        self._on_connect_cb = callback

    def set_on_ticks(self, callback: Callable[[list[dict]], None]) -> None:
        self._on_ticks_cb = callback

    def set_on_disconnect(self, callback: Callable[[int, str], None]) -> None:
        self._on_disconnect_cb = callback

    async def connect(self) -> None:
        """Create and start KiteTicker in background thread (non-blocking)."""
        api_key = self._client._kite.api_key  # type: ignore[attr-defined]
        access_token = self._client._kite.access_token  # type: ignore[attr-defined]

        self._ticker = KiteTicker(api_key, access_token)

        def _on_connect(ws: object, response: object) -> None:
            if self._on_connect_cb:
                self._on_connect_cb()

        def _on_ticks(ws: object, ticks: list[dict]) -> None:
            if self._on_ticks_cb:
                self._on_ticks_cb(ticks)

        def _on_close(ws: object, code: int, reason: str) -> None:
            if self._on_disconnect_cb:
                self._on_disconnect_cb(code, reason)

        self._ticker.on_connect = _on_connect
        self._ticker.on_ticks = _on_ticks
        self._ticker.on_close = _on_close

        # threaded=True spawns a daemon thread and returns immediately.
        # The ticker runs its own Twisted reactor in that thread for the
        # lifetime of the WebSocket connection.
        self._ticker.connect(threaded=True)

    async def subscribe(self, tokens: list[int]) -> None:
        if self._ticker is None:
            raise RuntimeError("ZerodhaStream: not connected")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ticker.subscribe, tokens)
        await loop.run_in_executor(None, self._ticker.set_mode, self._ticker.MODE_FULL, tokens)

    async def close(self) -> None:
        if self._ticker is not None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ticker.close)
            self._ticker = None
