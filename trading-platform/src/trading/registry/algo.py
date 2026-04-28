from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.messaging import AbstractRegistry
from trading.core.schemas import CandleEvent, InstrumentType, SignalEvent
from trading.core.tasks import fire
from trading.features.base import FeatureEngine
from trading.storage.base import AbstractRepository
from trading.strategy.base import Strategy

logger = logging.getLogger(__name__)


class AlgoConfig(BaseModel):
    """
    Configuration for the algo/strategy stage.

    instrument_strategy_map: maps each instrument symbol to the strategy_id
        to use for that symbol, resolved at runtime.
        e.g. {"INFY": "ema_crossover", "TCS": "rsi_mean_reversion"}

    instrument_feature_map: maps each instrument symbol to the feature_engine_id.
        e.g. {"INFY": "technical", "TCS": "technical"}
    """

    instrument_strategy_map: dict[str, str]
    instrument_feature_map: dict[str, str]
    equity: float = Field(default=100_000.0, gt=0)
    warmup_candles: int = Field(default=200, gt=0)
    algo_name: str = "default"
    instrument_types: dict[str, str] = Field(default_factory=dict)  # symbol → InstrumentType value


@dataclass
class _AlgoInstance:
    strategy: Strategy
    feature_engine: FeatureEngine
    instrument_type: InstrumentType
    bars_seen: int = 0
    warmed_up: bool = False
    last_signal_at: str | None = None


class AlgoRegistry(AbstractRegistry):
    """
    Runs one or more strategy instances — one per instrument in the config.

    Each instrument gets its own Strategy + FeatureEngine pair, resolved from
    the IDs in AlgoConfig at construction time. Supports fan-out: a single
    CandleEvent can produce signals from multiple instruments if the same
    candle applies to more than one.

    handle(candle) returns a list of SignalEvents (empty if no signal fired).
    """

    def __init__(
        self,
        config: AlgoConfig,
        session_factory: async_sessionmaker[AsyncSession],
        repo: AbstractRepository,
        algos: dict[str, _AlgoInstance] | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._repo = repo
        self._algos: dict[str, _AlgoInstance] = algos if algos is not None else {}
        if not self._algos:
            logger.warning(
                "AlgoRegistry[%s]: no algo instances — will produce no signals",
                config.algo_name,
            )

    # ------------------------------------------------------------------
    # AbstractRegistry
    # ------------------------------------------------------------------

    async def handle(self, candle: CandleEvent) -> list[SignalEvent]:
        """
        Feed a candle into every matching strategy instance.

        Returns a list of SignalEvents — empty if no strategy fired.
        """
        instance = self._algos.get(candle.symbol)
        if instance is None:
            return []

        instance.bars_seen += 1
        df = instance.feature_engine.update(candle)
        signal = instance.strategy.on_candle(candle.symbol, instance.instrument_type, df)

        if signal is None:
            if candle.tick_log_id != 0:
                fire(self._upsert_state(candle.symbol, instance))
            return []

        instance.warmed_up = True
        instance.last_signal_at = datetime.now(UTC).isoformat()

        signal_event = SignalEvent(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            instrument_type=signal.instrument_type,
            side=signal.side,
            strategy_id=signal.strategy_id,
            signal_type=signal.signal_type,
            stop_distance=signal.stop_distance,
            timestamp=signal.timestamp,
            tick_log_id=candle.tick_log_id,
        )

        fire(self._log_signal(signal_event, self._config.algo_name))
        if candle.tick_log_id != 0:
            fire(self._upsert_state(candle.symbol, instance))

        logger.info(
            "AlgoRegistry[%s]: signal %s %s %s",
            self._config.algo_name, signal.signal_id, signal.side, signal.symbol,
        )
        return [signal_event]

    # ------------------------------------------------------------------
    # State persistence + decision logging (fire-and-forget)
    # ------------------------------------------------------------------

    async def _upsert_state(self, symbol: str, instance: _AlgoInstance) -> None:
        warmup_complete = instance.warmed_up or instance.bars_seen >= self._config.warmup_candles
        state: dict[str, object] = {
            "bars_seen": instance.bars_seen,
            "warmup_candles": self._config.warmup_candles,
            "warmup_complete": warmup_complete,
            "bars_remaining": 0 if warmup_complete else max(0, self._config.warmup_candles - instance.bars_seen),
            "last_signal_at": instance.last_signal_at,
            **instance.strategy.get_state(),
        }
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.upsert_algo_state(
                        session, f"{self._config.algo_name}:{symbol}", state
                    )
        except Exception:
            logger.debug("AlgoRegistry: state upsert failed for %s:%s", self._config.algo_name, symbol)

    async def _log_signal(self, event: SignalEvent, algo_name: str) -> None:
        if event.tick_log_id == 0:
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
                            "algo_name": algo_name,
                        },
                        algo_name=algo_name,
                        signal_id=event.signal_id,
                    )
        except Exception:
            logger.warning("AlgoRegistry: decision log failed for signal %s", event.signal_id)
