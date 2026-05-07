from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.messaging import AbstractRegistry
from trading.core.schemas import CandleEvent, InstrumentType, SignalEvent
from trading.core.tasks import fire
from trading.indicators.context import IndicatorContext
from trading.indicators.polars_store import PolarsStore
from trading.storage.base import AbstractRepository
from trading.strategy.base import Strategy

logger = logging.getLogger(__name__)


class AlgoConfig(BaseModel):
    instrument_strategy_map: dict[str, str]
    equity: float = Field(default=100_000.0, gt=0)
    warmup_candles: int = Field(default=200, gt=0)
    algo_name: str = "default"
    instrument_types: dict[str, str] = Field(default_factory=dict)


@dataclass
class _AlgoInstance:
    strategy: Strategy
    instrument_type: InstrumentType
    bars_seen: int = 0
    warmed_up: bool = False
    last_signal_at: str | None = None


class AlgoRegistry(AbstractRegistry):
    """
    Runs one strategy instance per instrument.

    Each CandleEvent is pushed into the shared PolarsStore so indicator
    objects can fetch() the latest bars, then strategy.on_candle() is called.
    """

    def __init__(
        self,
        config: AlgoConfig,
        session_factory: async_sessionmaker[AsyncSession],
        repo: AbstractRepository,
        algos: dict[str, _AlgoInstance] | None = None,
        store: PolarsStore | None = None,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._repo = repo
        self._algos: dict[str, _AlgoInstance] = algos if algos is not None else {}
        self._store: PolarsStore = store if store is not None else PolarsStore()
        self._indicator_context: IndicatorContext = IndicatorContext(self._store)

        if not self._algos:
            logger.warning(
                "AlgoRegistry[%s]: no algo instances — will produce no signals",
                config.algo_name,
            )

    def set_indicator_context(self, context: IndicatorContext) -> None:
        self._indicator_context = context

    async def handle(self, candle: CandleEvent) -> list[SignalEvent]:
        instance = self._algos.get(candle.symbol)
        if instance is None:
            return []

        # Push candle into the in-memory store so indicators can fetch it
        self._store.push(
            candle.symbol,
            candle.interval,
            {
                "symbol": candle.symbol,
                "interval": candle.interval,
                "ts": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            },
        )

        instance.bars_seen += 1

        # Provide store to strategy (no-op if already set — strategies cache it)
        instance.strategy.set_store(self._indicator_context.get_store())

        signal = await instance.strategy.on_candle(candle.symbol, instance.instrument_type, candle)

        if signal is not None:
            instance.warmed_up = True
            instance.last_signal_at = datetime.now(UTC).isoformat()

        fire(self._upsert_state(instance))

        if signal is None:
            return []

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

        logger.info(
            "AlgoRegistry[%s]: signal %s %s %s",
            self._config.algo_name, signal.signal_id, signal.side, signal.symbol,
        )
        return [signal_event]

    async def _upsert_state(self, instance: _AlgoInstance) -> None:
        warmup_complete = instance.warmed_up or instance.bars_seen >= self._config.warmup_candles
        state: dict[str, object] = {
            "bars_seen": instance.bars_seen,
            "warmup_candles": self._config.warmup_candles,
            "warmup_complete": warmup_complete,
            "bars_remaining": (
                0 if warmup_complete else max(0, self._config.warmup_candles - instance.bars_seen)
            ),
            "last_signal_at": instance.last_signal_at,
            **instance.strategy.get_state(),
        }
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await self._repo.upsert_algo_state(
                        session, self._config.algo_name, state
                    )
        except Exception:
            logger.debug("AlgoRegistry: state upsert failed for %s", self._config.algo_name)

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
