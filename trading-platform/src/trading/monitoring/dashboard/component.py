from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.engine.component import Component
from trading.monitoring.dashboard.app import build_app

logger = logging.getLogger(__name__)


class DashboardServer(Component):
    """
    Lifecycle wrapper that runs the FastAPI dashboard inside the Runtime.

    Starts last in the component list so all other components are running
    before the dashboard begins serving requests. Stops cleanly when the
    runtime shuts down by signalling uvicorn's ``should_exit`` flag.

    Access the dashboard at http://<host>:<port>/ (default 127.0.0.1:8080).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        super().__init__(name="dashboard")
        self._session_factory = session_factory
        self._host = host
        self._port = port
        self._server: object | None = None  # uvicorn.Server, set in _setup

    async def _setup(self) -> None:
        import uvicorn

        app = build_app(self._session_factory)
        config = uvicorn.Config(
            app=app,
            host=self._host,
            port=self._port,
            log_level="warning",  # keep uvicorn quiet; our logger handles app logs
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        logger.info("DashboardServer: ready on http://%s:%d", self._host, self._port)

    async def _run(self) -> None:
        # serve() blocks until should_exit is set
        await self._server.serve()  # type: ignore[union-attr]

    async def _teardown(self) -> None:
        if self._server is not None:
            self._server.should_exit = True  # type: ignore[union-attr]
            logger.info("DashboardServer: shutdown requested")
