"""
Trading platform entry point.

Lifecycle
---------
1. Build the DI container (connects DB engine + Redis client).
2. Run Alembic migrations to bring the schema up to date.
3. Resolve the Runtime and Scheduler from the container.
4. Start the APScheduler (fires Runtime.start at 09:15 IST, Runtime.stop at 15:30 IST).
5. If we are already inside market hours on startup, fire Runtime.start immediately.
6. Sleep forever — the scheduler drives everything from here.

The process exits cleanly on SIGTERM / KeyboardInterrupt; the DI container
disposes of all async resources (engine, redis) on context-manager exit.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from datetime import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from anyio import sleep_forever

from trading.di.container import build_container
from trading.engine.runtime import AbstractRuntime
from trading.engine.scheduler import Scheduler

_LOG_DIR = Path("logs")
_LOG_DIR.mkdir(exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Stream handler — live output to terminal, force UTF-8 on Windows
_stream_handler = logging.StreamHandler(
    open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)
)
_stream_handler.setFormatter(_fmt)

# Rotating file handler — 10 MB per file, keep 10 files (~100 MB max)
_file_handler = RotatingFileHandler(
    _LOG_DIR / "trading.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=10,
    encoding="utf-8",
)
_file_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])
logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def _check_port_free(port: int) -> None:
    """Exit with a clear message if *port* is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", port)) != 0:
            return  # port is free

    # Find the owning PID on Windows for a helpful error message
    pid_hint = ""
    if sys.platform == "win32":
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid_hint = f" (PID {line.split()[-1]})"
                break

    sys.exit(
        f"ERROR: port {port} is already in use{pid_hint}.\n"
        f"Stop the process holding it and rerun:  uv run start"
    )


def _run_migrations() -> None:
    """Apply pending Alembic migrations synchronously before starting async code."""
    logger.info("Running Alembic migrations…")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("Alembic migration failed:\n%s", result.stderr)
        raise RuntimeError("DB migration failed — aborting startup")
    logger.info("Migrations complete.")


def _is_market_hours() -> bool:
    """Return True if the current IST time is within market hours on a weekday."""
    from datetime import datetime

    now_ist = datetime.now(_IST)
    if now_ist.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now_ist.time()
    return _MARKET_OPEN <= t < _MARKET_CLOSE


async def _main() -> None:
    from trading.config.settings import get_settings
    settings = get_settings()
    if settings.dashboard_enabled:
        _check_port_free(settings.dashboard_port)

    _run_migrations()

    async with build_container() as container:
        runtime: AbstractRuntime = await container.get(AbstractRuntime)
        scheduler: Scheduler = await container.get(Scheduler)

        scheduler.start()
        logger.info("Scheduler started.")

        if _is_market_hours():
            logger.info("Market is currently open — starting runtime immediately.")
            asyncio.get_event_loop().create_task(runtime.start())
        else:
            logger.info("Outside market hours — waiting for next 09:15 IST trigger.")

        try:
            await sleep_forever()
        finally:
            scheduler.stop()
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down.")
