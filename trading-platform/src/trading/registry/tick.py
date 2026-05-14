from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from trading.broker.base.broker_stream import BrokerStream
from trading.core.messaging import AbstractRegistry
from trading.core.models import Instrument
from trading.core.schemas import InstrumentType, TickEvent
from trading.storage.stores.audit import AbstractAuditStore

logger = logging.getLogger(__name__)

_CIRCUIT_TIMEOUT_SECS = 30.0


class TickConfig(BaseModel):
    """Configuration for the tick ingestion stage."""

    model_config = {"arbitrary_types_allowed": True}

    instruments: list[Instrument]
    exec_id: str = "direct"  # "paper" | "direct"


class CircuitBreaker:
    """
    Tracks whether the ingestor WebSocket is healthy.

    Opened by KiteIngestor after 30s of disconnection.
    Closed on reconnect. Read by RiskRegistry before placing orders.
    """

    def __init__(self) -> None:
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def is_open(self) -> bool:
        return self._open


class TickRegistry(AbstractRegistry):
    """
    Ingests raw WebSocket ticks, persists them to DB, and produces TickEvents.

    Owns the CircuitBreaker — opens it after prolonged disconnect, closes it
    on reconnect. RiskRegistry receives a reference to this same instance.

    Call handle(raw_tick_dict) for each tick arriving from the broker stream.
    Returns a TickEvent on success, None if the tick is invalid or unknown.
    """

    def __init__(
        self,
        config: TickConfig,
        stream: BrokerStream,
        audit: AbstractAuditStore,
        circuit_timeout_secs: float = _CIRCUIT_TIMEOUT_SECS,
    ) -> None:
        self._config = config
        self._stream = stream
        self._audit = audit
        self._circuit_timeout_secs = circuit_timeout_secs

        self.circuit = CircuitBreaker()
        self._circuit_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._token_type: dict[int, InstrumentType] = {
            inst.token: InstrumentType(inst.instrument_type) for inst in config.instruments
        }
        self._token_symbol: dict[int, str] = {
            inst.token: inst.symbol for inst in config.instruments
        }

    # ------------------------------------------------------------------
    # AbstractRegistry
    # ------------------------------------------------------------------

    async def handle(self, raw: dict) -> TickEvent | None:
        """
        Validate and persist one raw tick dict from the broker WebSocket.

        Returns a TickEvent with a real DB-assigned tick_log_id, or None
        if the tick is for an unknown instrument or fails validation.
        """
        token: int | None = raw.get("instrument_token")  # type: ignore[assignment]
        if token is None:
            return None

        instrument_type = self._token_type.get(token)
        if instrument_type is None:
            return None

        symbol = self._token_symbol[token]

        try:
            raw_event = TickEvent(
                instrument_token=token,
                instrument_type=instrument_type,
                last_price=raw.get("last_price", 0),
                volume=raw.get("volume_traded", raw.get("volume", 0)),
                timestamp=datetime.now(UTC),
                tick_log_id=0,
            )
        except ValidationError:
            logger.warning("TickRegistry: invalid tick for token %s — %r", token, raw)
            return None

        try:
            tick_log_id = await self._audit.log_tick(raw_event, symbol)
        except Exception as exc:
            logger.warning("TickRegistry: DB persist failed for token %s — %s", token, exc)
            tick_log_id = -1

        return TickEvent(
            instrument_token=token,
            instrument_type=instrument_type,
            last_price=raw_event.last_price,
            volume=raw_event.volume,
            timestamp=raw_event.timestamp,
            tick_log_id=tick_log_id,
        )

    # ------------------------------------------------------------------
    # Circuit-breaker helpers (called by KiteIngestor WebSocket callbacks)
    # ------------------------------------------------------------------

    def on_connected(self) -> None:
        """Call when the WebSocket (re)connects."""
        if self._circuit_task is not None and not self._circuit_task.done():
            self._circuit_task.cancel()
        self.circuit.close()
        logger.info("TickRegistry: WebSocket connected — circuit closed")

    def on_disconnected(self) -> None:
        """Call when the WebSocket disconnects."""
        logger.warning("TickRegistry: WebSocket disconnected — starting circuit timer")
        loop = self._loop or asyncio.get_event_loop()
        self._loop = loop
        if self._circuit_task is None or self._circuit_task.done():
            self._circuit_task = loop.create_task(self._open_circuit_after_timeout())

    async def _open_circuit_after_timeout(self) -> None:
        try:
            await asyncio.sleep(self._circuit_timeout_secs)
            self.circuit.open()
            logger.error(
                "TickRegistry: circuit OPEN after %.0fs disconnect", self._circuit_timeout_secs
            )
        except asyncio.CancelledError:
            pass  # reconnected before timeout

    # ------------------------------------------------------------------
    # Public accessors (avoid private attribute access from KiteIngestor)
    # ------------------------------------------------------------------

    def get_tokens(self) -> list[int]:
        """Return all instrument tokens registered for subscription."""
        return list(self._token_type.keys())

    def get_symbol(self, token: int) -> str | None:
        """Return the trading symbol for a given instrument token, or None."""
        return self._token_symbol.get(token)

    def cancel_circuit_task(self) -> None:
        """Cancel any pending circuit-open timer (called by KiteIngestor on teardown)."""
        if self._circuit_task is not None and not self._circuit_task.done():
            self._circuit_task.cancel()
