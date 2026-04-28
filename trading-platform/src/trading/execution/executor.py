from __future__ import annotations

import logging

from anyio import sleep_forever

from trading.engine.component import Component
from trading.registry.exec import ExecRegistry

logger = logging.getLogger(__name__)


class OrderExecutor(Component):
    """
    Lifecycle wrapper around ExecRegistry.

    _setup is a no-op (ExecRegistry is ready at construction time).
    _run sleeps forever — orders are fed via on_order() from RiskController.
    """

    def __init__(self, exec_registry: ExecRegistry) -> None:
        super().__init__(name=f"order_executor[{exec_registry._config.exec_id}]")
        self._registry = exec_registry

    async def _setup(self) -> None:
        logger.info("OrderExecutor: ready (exec_id=%s)", self._registry._config.exec_id)

    async def _run(self) -> None:
        await sleep_forever()
