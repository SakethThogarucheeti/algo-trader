from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from anyio import sleep_forever
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.messaging import MessageBus
from trading.core.schemas import CandleEvent, InstrumentType, SignalEvent
from trading.engine.component import Component
from trading.features.base import FeatureEngine
from trading.storage.base import AbstractRepository
from trading.strategy.base import Strategy

logger = logging.getLogger(__name__)


class AlgoRunner(Component):
    """
    Self-contained trading engine for one algo.

    Subscribes to ``candle:{symbol}:{interval}`` for every instrument/interval
    pair in the algo. On each completed candle:

    1. Updates the ``FeatureEngine`` to compute indicators.
    2. Passes the enriched DataFrame to the ``Strategy``.
    3. If the strategy returns a ``Signal``, publishes it to
       ``signals:{algo_name}`` for the algo's ``RiskController`` to evaluate.
    4. Logs a ``SIGNAL_GENERATED`` decision record (fire-and-forget).
    5. Upserts ``algo_state`` with live strategy internals (fire-and-forget).

    Channel scoping ensures signals from this algo only flow to its own
    RiskController and do not cross into other algos' pipelines.
    """

    def __init__(
        self,
        bus: MessageBus,
        algo_name: str,
        symbols: list[str],
        instrument_types: dict[str, InstrumentType],  # symbol → type
        intervals: list[str],
        strategy: Strategy,
        feature_engine: FeatureEngine,
        session_factory: async_sessionmaker[AsyncSession],
        repo: AbstractRepository,
        warmup_candles: int = 30,
    ) -> None:
        super().__init__(name=f"algo_runner[{algo_name}]")
        self._bus = bus
        self._algo_name = algo_name
        self._symbols = set(symbols)
        self._instrument_types = instrument_types
        self._intervals = intervals
        self._strategy = strategy
        self._feature_engine = feature_engine
        self._session_factory = session_factory
        self._repo = repo
        self._signals_channel = f"signals:{algo_name}"
        self._warmup_candles = warmup_candles
        self._bars_seen: int = 0
        self._warmed_up: bool = False  # flips True the first time strategy produces a signal
        self._last_signal_at: str | None = None

    # ------------------------------------------------------------------
    # Component lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        # Restore warmup state from DB so restarts don't reset the countdown
        try:
            async with self._session_factory() as session:
                prior = await self._repo.get_algo_configs_with_state(session)
                for a in prior:
                    if a["name"] == self._algo_name:
                        state = a.get("state", {})
                        if state.get("warmup_complete"):
                            self._warmed_up = True
                            self._bars_seen = self._warmup_candles
                        if state.get("last_signal_at"):
                            self._last_signal_at = state["last_signal_at"]
                        break
        except Exception:
            pass  # non-fatal — will re-warm naturally

        for symbol in self._symbols:
            for interval in self._intervals:
                self._bus.subscribe(
                    f"candle:{symbol}:{interval}",
                    CandleEvent,
                    self._on_candle,
                )
        logger.info(
            "AlgoRunner[%s]: subscribed to %d symbols for %d intervals (warmed_up=%s)",
            self._algo_name,
            len(self._symbols),
            len(self._intervals),
            self._warmed_up,
        )

    async def _run(self) -> None:
        await sleep_forever()

    # ------------------------------------------------------------------
    # Candle handler
    # ------------------------------------------------------------------

    async def _on_candle(self, event: CandleEvent) -> None:
        if event.symbol not in self._symbols:
            return  # candle for a symbol not in this algo — skip

        self._bars_seen += 1

        # 1. Update feature engine (computes indicators)
        df = self._feature_engine.update(event)

        # 2. Ask strategy for a signal
        instrument_type = self._instrument_types.get(event.symbol, event.instrument_type)
        signal = self._strategy.on_candle(event.symbol, instrument_type, df)

        if signal is not None:
            self._warmed_up = True
            self._last_signal_at = datetime.now(UTC).isoformat()

            # 3. Publish signal to this algo's scoped channel
            signal_event = SignalEvent(
                signal_id=signal.signal_id,
                symbol=signal.symbol,
                instrument_type=signal.instrument_type,
                side=signal.side,
                strategy_id=signal.strategy_id,
                signal_type=signal.signal_type,
                stop_distance=signal.stop_distance,
                timestamp=signal.timestamp,
                tick_log_id=event.tick_log_id,  # propagate root tick id
            )
            await self._bus.publish(self._signals_channel, signal_event)
            logger.info(
                "AlgoRunner[%s]: strategy %s generated signal %s for %s",
                self._algo_name,
                self._strategy.id,
                signal.signal_id,
                signal.symbol,
            )

            # 4. Log the SIGNAL_GENERATED decision (fire-and-forget audit trail)
            asyncio.get_running_loop().create_task(self._log_signal_decision(signal_event))

        # 5. Upsert algo state for dashboard (fire-and-forget, live candles only)
        if event.tick_log_id != 0:
            asyncio.get_running_loop().create_task(self._upsert_state())

    # ------------------------------------------------------------------
    # State persistence (fire-and-forget)
    # ------------------------------------------------------------------

    async def _upsert_state(self) -> None:
        warmup_complete = self._warmed_up or self._bars_seen >= self._warmup_candles
        state: dict[str, object] = {
            "bars_seen": self._bars_seen,
            "warmup_candles": self._warmup_candles,
            "warmup_complete": warmup_complete,
            "bars_remaining": 0 if warmup_complete else max(0, self._warmup_candles - self._bars_seen),
            "last_signal_at": self._last_signal_at,
            **self._strategy.get_state(),
        }
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.upsert_algo_state(session, self._algo_name, state)
        except Exception:
            logger.debug("AlgoRunner[%s]: state upsert failed", self._algo_name)

    # ------------------------------------------------------------------
    # Decision logging (fire-and-forget)
    # ------------------------------------------------------------------

    async def _log_signal_decision(self, event: SignalEvent) -> None:
        if event.tick_log_id == 0:
            # Backtest candles use tick_log_id=0; no real tick_logs row exists — skip.
            return
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.log_decision(
                        session,
                        step="SIGNAL_GENERATED",
                        symbol=event.symbol,
                        tick_log_id=event.tick_log_id,
                        context={
                            "strategy_id": event.strategy_id,
                            "side": event.side.value,
                            "signal_type": event.signal_type.value,
                            "stop_distance": event.stop_distance,
                            "algo_name": self._algo_name,
                        },
                        algo_name=self._algo_name,
                        signal_id=event.signal_id,
                    )
        except Exception:
            logger.warning(
                "AlgoRunner[%s]: decision log failed for signal %s — audit trail gap",
                self._algo_name,
                event.signal_id,
            )
