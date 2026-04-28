from __future__ import annotations

import logging

from anyio import sleep_forever

from trading.engine.component import Component
from trading.registry.algo import AlgoRegistry

logger = logging.getLogger(__name__)


class AlgoRunner(Component):
    """
    Lifecycle wrapper around AlgoRegistry.

    _setup is a no-op (AlgoRegistry is ready at construction time).
    _run sleeps forever — candles are fed via on_candle() from CandleAggregator.
    """

    def __init__(self, algo_registry: AlgoRegistry) -> None:
        name = f"algo_runner[{algo_registry._config.algo_name}]"
        super().__init__(name=name)
        self._registry = algo_registry

    async def _setup(self) -> None:
        logger.info(
            "AlgoRunner[%s]: ready with %d instruments",
            self._registry._config.algo_name,
            len(self._registry._algos),
        )

    async def _run(self) -> None:
        await sleep_forever()
