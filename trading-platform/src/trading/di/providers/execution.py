from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.broker.paper_broker import PriceStore
from trading.core.messaging import MessageBus
from trading.execution.base import ExecutionEngine
from trading.execution.executor import DirectExecutionEngine
from trading.storage.repository import Repository


def make_execution_engine(
    engine_id: str,
    *,
    bus: MessageBus,
    broker: Broker,
    repo: Repository,
    sf: async_sessionmaker[AsyncSession],
    price_store: PriceStore | None,
) -> ExecutionEngine:
    """Resolve an execution_engine_id string to an ExecutionEngine instance.

    To add a new execution engine: add a case here and a class file under
    trading/execution/. No registry dict to maintain.
    """
    match engine_id:
        case "direct":
            return DirectExecutionEngine(
                bus=bus,
                broker=broker,
                repo=repo,
                session_factory=sf,
                paper_price_store=price_store,
            )
        case _:
            raise ValueError(
                f"Unknown execution_engine_id: {engine_id!r}. "
                f"Add a case to make_execution_engine() in di/providers/execution.py."
            )
