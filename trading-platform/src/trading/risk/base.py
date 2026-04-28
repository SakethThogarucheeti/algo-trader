from __future__ import annotations

import logging

from anyio import sleep_forever

from trading.engine.component import Component
from trading.registry.risk import RiskRegistry

logger = logging.getLogger(__name__)


class RiskController(Component):
    """
    Lifecycle wrapper around RiskRegistry.

    _setup is a no-op (RiskRegistry is ready at construction time).
    _run sleeps forever — signals are fed via on_signal() from AlgoRunner.
    """

    def __init__(self, risk_registry: RiskRegistry) -> None:
        super().__init__(name="risk_controller")
        self._registry = risk_registry

    async def _setup(self) -> None:
        logger.info("RiskController: ready (rc_id=%s)", self._registry._config.rc_id)

    async def _run(self) -> None:
        await sleep_forever()
