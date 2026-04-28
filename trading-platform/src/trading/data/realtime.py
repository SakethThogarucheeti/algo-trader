from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from anyio import sleep_forever
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker_stream import BrokerStream
from trading.core.messaging import MessageBus
from trading.core.models import Instrument
from trading.core.schemas import InstrumentType, TickEvent
from trading.engine.component import Component
from trading.storage.repository import Repository

logger = logging.getLogger(__name__)

_CIRCUIT_FLAG = "circuit:ingestor:open"
_CIRCUIT_TTL_SECS = 90
_CONNECT_TIMEOUT_SECS = 30.0  # max wait for initial WebSocket on_connect callback


class KiteIngestor(Component):
    """
    Maintains the broker WebSocket connection and publishes validated
    TickEvents to Redis channel ``tick:{instrument_token}``.

    Tick ID assignment
    ------------------
    Every tick is persisted to ``tick_logs`` before being published to Redis.
    The DB-assigned ``id`` is set on the TickEvent as ``tick_log_id`` so all
    downstream components (CandleAggregator, AlgoRunner, RiskController) can
    trace their decisions back to the originating tick.

    The INSERT uses ``session.flush()`` (not commit) to obtain the id
    immediately, then schedules the commit as a background task so the commit
    round-trip is off the critical path. The tick is not published until the
    flush completes and the id is assigned — this ensures tick_log_id is always
    a real, valid database id on every published TickEvent.

    Lifecycle
    ---------
    _setup:   register WS callbacks → connect → wait for on_connect → subscribe tokens
    _run:     sleep_forever (ticks arrive via callbacks)
    _teardown: cancel circuit-open task → close stream
    """

    def __init__(
        self,
        stream: BrokerStream,
        bus: MessageBus,
        instruments: list[Instrument],
        session_factory: async_sessionmaker[AsyncSession],
        repo: Repository,
        circuit_timeout_secs: float = 30.0,
        price_store: object | None = None,  # PriceStore | None
    ) -> None:
        super().__init__(name="kite_ingestor")
        self._stream = stream
        self._bus = bus
        self._session_factory = session_factory
        self._repo = repo
        self._circuit_timeout_secs = circuit_timeout_secs
        self._price_store = price_store
        # token → InstrumentType for quick lookup during tick processing
        self._token_type: dict[int, InstrumentType] = {
            inst.token: InstrumentType(inst.instrument_type) for inst in instruments
        }
        # token → symbol for price store updates and tick logging
        self._token_symbol: dict[int, str] = {inst.token: inst.symbol for inst in instruments}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected: asyncio.Event | None = None
        self._circuit_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Component lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._connected = asyncio.Event()

        self._stream.set_on_connect(self._on_ws_connect)
        self._stream.set_on_ticks(self._on_ws_ticks)
        self._stream.set_on_disconnect(self._on_ws_disconnect)

        await self._stream.connect()
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=_CONNECT_TIMEOUT_SECS)
        except TimeoutError as err:
            raise RuntimeError(
                f"KiteIngestor: WebSocket did not connect within {_CONNECT_TIMEOUT_SECS}s — "
                "check broker credentials and network"
            ) from err
        tokens = list(self._token_type.keys())
        if tokens:
            await self._stream.subscribe(tokens)
            logger.info("KiteIngestor: connected and subscribed to %d tokens", len(tokens))
        else:
            logger.warning(
                "KiteIngestor: no instruments configured — "
                "connected but not subscribed to any tokens"
            )

    async def _run(self) -> None:
        await sleep_forever()

    async def _teardown(self) -> None:
        if self._circuit_task is not None and not self._circuit_task.done():
            self._circuit_task.cancel()
        await self._stream.close()

    # ------------------------------------------------------------------
    # WebSocket thread callbacks → bridge to asyncio event loop
    # ------------------------------------------------------------------

    def _on_ws_connect(self) -> None:
        """Called from WS thread when connection is established."""
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._on_connected)

    def _on_connected(self) -> None:
        """Runs on the event loop thread."""
        if self._connected is not None:
            self._connected.set()
        if self._circuit_task is not None and not self._circuit_task.done():
            self._circuit_task.cancel()
        if self._loop is not None:
            self._loop.create_task(self._bus.delete_flag(_CIRCUIT_FLAG))
        logger.info("KiteIngestor: WebSocket connected")

    def _on_ws_ticks(self, ticks: list[dict]) -> None:
        """Called from WS thread with a batch of raw tick dicts."""
        if self._loop is None:
            return
        for tick in ticks:
            asyncio.run_coroutine_threadsafe(self._handle_tick(tick), self._loop)

    def _on_ws_disconnect(self, code: int, reason: str) -> None:
        """Called from WS thread on disconnect."""
        logger.warning("KiteIngestor: disconnected code=%s reason=%r", code, reason)
        assert self._loop is not None
        self._loop.call_soon_threadsafe(self._schedule_circuit_open)

    def _schedule_circuit_open(self) -> None:
        """Runs on the event loop. Starts the circuit-breaker timer."""
        if self._circuit_task is None or self._circuit_task.done():
            assert self._loop is not None
            self._circuit_task = self._loop.create_task(self._open_circuit_after_timeout())

    # ------------------------------------------------------------------
    # Async helpers (run on event loop)
    # ------------------------------------------------------------------

    async def _handle_tick(self, raw: dict) -> None:
        """
        Validate a raw tick dict, persist it, and publish as TickEvent.

        The tick_log_id is assigned by the DB flush and set on the event
        before publishing. tick_log_id is never None on a published event.
        """
        token: int | None = raw.get("instrument_token")  # type: ignore[assignment]
        if token is None:
            return

        instrument_type = self._token_type.get(token)
        if instrument_type is None:
            logger.debug("KiteIngestor: unknown token %s — skipping", token)
            return

        symbol = self._token_symbol.get(token, "")

        try:
            # Build event without tick_log_id first (id not yet assigned)
            raw_event = TickEvent(
                instrument_token=token,
                instrument_type=instrument_type,
                last_price=raw.get("last_price", 0),
                volume=raw.get("volume_traded", raw.get("volume", 0)),
                timestamp=datetime.now(UTC),
                tick_log_id=0,  # placeholder, overwritten below
            )
        except ValidationError:
            logger.warning("KiteIngestor: invalid tick data for token %s — %r", token, raw)
            return

        # Persist the tick and get the DB-assigned id.
        # We open a session, flush (sends INSERT and gets RETURNING id),
        # then commit asynchronously so the commit round-trip is off the
        # critical path. The event is not published until flush completes.
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    tick_log_id = await self._repo.log_tick(session, raw_event, symbol)
        except Exception as exc:
            logger.warning(
                "KiteIngestor: failed to persist tick for token %s — %s; publishing without DB id",
                token,
                exc,
            )
            # Fall back to a sentinel value so the event can still flow through
            # the pipeline. Decision logs downstream will fail their FK constraint
            # and be silently dropped, but trading is not affected.
            tick_log_id = -1

        # Reconstruct event with the real tick_log_id
        event = TickEvent(
            instrument_token=token,
            instrument_type=instrument_type,
            last_price=raw_event.last_price,
            volume=raw_event.volume,
            timestamp=raw_event.timestamp,
            tick_log_id=tick_log_id,
        )

        await self._bus.publish(f"tick:{token}", event)

        # Keep price store current for paper trading fill simulation
        if self._price_store is not None and symbol:
            self._price_store.update(symbol, event.last_price)  # type: ignore[attr-defined]

    async def _open_circuit_after_timeout(self) -> None:
        """Set the circuit breaker flag after being disconnected too long."""
        try:
            await asyncio.sleep(self._circuit_timeout_secs)
            await self._bus.set_flag(_CIRCUIT_FLAG, "1", ex=_CIRCUIT_TTL_SECS)
            logger.error(
                "KiteIngestor: circuit breaker OPEN after %.0fs disconnect",
                self._circuit_timeout_secs,
            )
        except asyncio.CancelledError:
            pass  # reconnected before timeout — don't set flag
