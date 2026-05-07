from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from trading.core.schemas import CandleEvent, InstrumentType, Side, SignalType

_log = logging.getLogger(__name__)


@dataclass
class Signal:
    """
    Trading signal produced by a strategy.

    ``stop_distance`` is used by the risk sizer to compute position size
    (e.g. ATR × multiplier). Must be > 0.

    For backtest reproducibility, pass ``timestamp=candle.timestamp`` explicitly
    when constructing a Signal. The default (``datetime.now(UTC)``) is correct
    for live trading but will vary across runs in backtests.

    ``signal_id`` is auto-generated; every call that returns a Signal produces
    a distinct UUID so the execution layer can deduplicate safely.
    """

    symbol: str
    instrument_type: InstrumentType
    side: Side
    strategy_id: str
    signal_type: SignalType
    stop_distance: float  # always > 0

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signal_id: UUID = field(default_factory=uuid4)


class Strategy(ABC):
    """
    Abstract base for all signal generators.

    ``on_candle`` MUST be a pure function — no broker calls, no DB writes,
    no network I/O. Side effects belong in the registry layer.
    """

    @property
    def id(self) -> str:
        """Alias of this strategy instance (delegates to the class attribute)."""
        return self.__class__.alias  # type: ignore[attr-defined]

    def set_store(self, store: object) -> None:
        """
        Called by AlgoRegistry before the first on_candle to supply the data store.

        Strategies that use indicators should override this to construct indicator
        instances using the provided store. Default implementation is a no-op for
        strategies that don't use indicators.
        """

    def get_state(self) -> dict[str, object]:
        """
        Return a snapshot of live strategy internals for the monitoring dashboard.

        Override to expose strategy-specific values (e.g. current EMA values).
        Merged into ``algo_state.state`` in Postgres after every candle.
        """
        return {}

    @abstractmethod
    async def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        candle: CandleEvent,
    ) -> Signal | None:
        """
        Called on every completed candle.

        Indicator instances (constructed via set_store()) are available here.
        Call ``await self.my_indicator.compute(params)`` to get the current value.

        Returns Signal or None.
        """
