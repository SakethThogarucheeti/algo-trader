from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import polars as pl

from trading.core.messaging import MessageBus
from trading.core.schemas import CandleEvent
from trading.data.candles import _SymbolConfig
from trading.engine.component import Component
from trading.engine.runtime import Runtime

logger = logging.getLogger(__name__)


class CandlePlayer(Component):
    """
    Replay historical OHLCV data as ``CandleEvent`` messages on the bus.

    Loads all (symbol × interval) DataFrames in ``_setup()``, merges them
    into a single globally time-sorted event queue, then replays each row
    as a ``CandleEvent`` on ``candle:{symbol}:{interval}`` in ``_run()``.

    After the last bar, calls ``runtime.stop()`` so the attached
    ``Runtime`` (and all its components) shuts down cleanly.

    No-lookahead guarantee
    ----------------------
    All events are sorted by ``date`` globally before replay. Each bar is
    published only after previous bars (across all symbols) in the same
    time bucket have been published. ``tick_log_id`` is set to 0 on every
    backtest candle — it is never written to the ``tick_logs`` table.

    Progress callback
    -----------------
    ``on_progress(bars_done)`` is called after every bar, allowing
    ``BacktestSession`` to emit ``SessionProgressEvent`` without coupling
    this component to the session layer.
    """

    def __init__(
        self,
        symbols: list[_SymbolConfig],
        intervals: list[str],
        start: datetime,
        end: datetime,
        runtime: Runtime,
        bus: MessageBus,
        on_progress: Callable[[int], Awaitable[None]],
        data: dict[tuple[str, str], pl.DataFrame],  # (symbol, interval) → OHLCV df
        replay_delay_secs: float = 0.0,
    ) -> None:
        super().__init__(name="candle_player")
        self._symbols = symbols
        self._intervals = intervals
        self._start = start
        self._end = end
        self._runtime = runtime
        self._bus = bus
        self._on_progress = on_progress
        self._data = data
        self._replay_delay_secs = replay_delay_secs
        self._event_queue: list[tuple[datetime, str, str, CandleEvent]] = []

    async def _setup(self) -> None:
        """Build the globally sorted event queue from pre-loaded DataFrames."""
        symbol_map = {sc.symbol: sc for sc in self._symbols}

        for (symbol, interval), df in self._data.items():
            sym_config = symbol_map.get(symbol)
            if sym_config is None:
                logger.warning("CandlePlayer: symbol %r not in symbols list — skipping", symbol)
                continue

            instr_type = sym_config.instrument_type

            for row in df.iter_rows(named=True):
                ts: datetime = row["date"]
                if not isinstance(ts, datetime):
                    # Polars may return date as a Python datetime already; guard anyway

                    ts = datetime.fromisoformat(str(ts)).replace(tzinfo=UTC)

                event = CandleEvent(
                    symbol=symbol,
                    instrument_type=instr_type,
                    interval=interval,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    timestamp=ts,
                    tick_log_id=0,  # backtest candles never write to tick_logs
                )
                self._event_queue.append((ts, symbol, interval, event))

        # Global sort by timestamp → no lookahead bias across symbols/intervals
        self._event_queue.sort(key=lambda x: x[0])
        logger.info(
            "CandlePlayer: loaded %d events across %d symbol-interval pairs",
            len(self._event_queue),
            len(self._data),
        )

    async def _run(self) -> None:
        bars_done = 0
        for _ts, symbol, interval, event in self._event_queue:
            channel = f"candle:{symbol}:{interval}"
            await self._bus.publish(channel, event)

            if self._replay_delay_secs > 0:
                await asyncio.sleep(self._replay_delay_secs)

            bars_done += 1
            try:
                await self._on_progress(bars_done)
            except Exception:
                logger.debug("CandlePlayer: on_progress callback raised", exc_info=True)

        logger.info("CandlePlayer: replay complete — %d bars published", bars_done)
        # Give subscribers a tick to process the last event before stopping
        await asyncio.sleep(0.05)
        self._runtime.stop()

    async def _teardown(self) -> None:
        logger.debug("CandlePlayer: teardown")
