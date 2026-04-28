from __future__ import annotations

import logging

from anyio import sleep_forever

from trading.engine.component import Component
from trading.registry.candle import CandleRegistry

logger = logging.getLogger(__name__)


class CandleAggregator(Component):
    """
    Lifecycle wrapper around CandleRegistry.

    _setup runs the warm-up (fetches historical candles from the broker) and
    replays them through any registered algo registries so strategies are
    pre-seeded before live ticks arrive.

    _run sleeps forever — live ticks are fed via KiteIngestor's on_tick callbacks.
    """

    def __init__(self, candle_registry: CandleRegistry) -> None:
        super().__init__(name="candle_aggregator")
        self._registry = candle_registry
        self._algo_callbacks: list = []  # list[AlgoRegistry] — avoid circular import

    def add_algo_registry(self, algo_registry: object) -> None:
        """Register an AlgoRegistry to receive warmup candles during _setup."""
        self._algo_callbacks.append(algo_registry)

    async def _setup(self) -> None:
        warmup_candles = await self._registry.warmup()
        if warmup_candles and self._algo_callbacks:
            logger.info(
                "CandleAggregator: replaying %d warmup candles through %d algo registry(s)",
                len(warmup_candles),
                len(self._algo_callbacks),
            )
            for candle in warmup_candles:
                for algo_reg in self._algo_callbacks:
                    try:
                        await algo_reg.handle(candle)
                    except Exception:
                        logger.exception(
                            "CandleAggregator: warmup replay error for %s", candle.symbol
                        )
        logger.info("CandleAggregator: warm-up complete")

    async def _run(self) -> None:
        await sleep_forever()
