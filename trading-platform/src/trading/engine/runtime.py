from __future__ import annotations

import logging

from anyio import CancelScope, create_task_group, sleep_forever

from trading.engine.component import Component

logger = logging.getLogger(__name__)


class Runtime:
    """
    Supervises a list of components with ordered startup and shutdown.

    Startup
    -------
    Components start in the order provided. Each component's ``_setup()``
    must complete (i.e. ``task_status.started()`` fires) before the next
    component begins its own ``_setup()``. This guarantees dependency-safe
    ordering (e.g. ingestor is RUNNING before candle aggregator subscribes).

    Shutdown
    --------
    Call ``stop()`` from the scheduler or externally — it cancels the
    internal CancelScope, triggering the finally block which stops all
    components in reverse order.
    """

    def __init__(self, components: list[Component]) -> None:
        self._components = components
        self._running = False
        self._cancel_scope: CancelScope | None = None

    async def start(self) -> None:
        """Start all components in order, then block until stop() is called."""
        self._running = True
        logger.info("Runtime: starting %d components", len(self._components))
        try:
            with CancelScope() as scope:
                self._cancel_scope = scope
                async with create_task_group() as tg:
                    for component in self._components:
                        await tg.start(component.start)
                        logger.info("Runtime: %s is RUNNING", component.name)

                    try:
                        await sleep_forever()
                    finally:
                        logger.info("Runtime: shutting down components")
                        for component in reversed(self._components):
                            try:
                                await component.stop()
                                logger.info("Runtime: %s stopped", component.name)
                            except Exception:
                                logger.exception("Runtime: error stopping %s", component.name)
        finally:
            self._cancel_scope = None
            self._running = False
            logger.info("Runtime: all components stopped")

    def stop(self) -> None:
        """Cancel the running task group, triggering orderly shutdown."""
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()
            logger.info("Runtime: stop requested")
        else:
            logger.warning("Runtime: stop() called but runtime is not running")

    @property
    def running(self) -> bool:
        return self._running
