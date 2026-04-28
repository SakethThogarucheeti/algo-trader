from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType


@dataclass
class Signal:
    """
    Trading signal produced by a strategy.

    ``stop_distance`` is used by the risk sizer to compute position size
    (e.g. ATR * multiplier). Must be > 0 — strategies must guard against
    returning a zero or NaN ATR.

    ``signal_id`` is auto-generated; every call that returns a Signal
    produces a distinct UUID so the execution layer can deduplicate safely.
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
    Abstract base for all stateless signal generators.

    Receives an enriched Polars DataFrame (OHLCV + indicators) and returns
    either a ``Signal`` or ``None``. Implementations MUST NOT call the broker,
    DB, Redis, or anything with side effects — on_candle is a pure function.

    Subclasses set ``id`` as a class attribute (e.g. ``id = "ema_crossover"``).
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier used to select this strategy by name in AlgoConfig."""

    def get_state(self) -> dict[str, object]:
        """
        Return a snapshot of live strategy internals for the monitoring dashboard.

        Override to expose strategy-specific values (e.g. current EMA values,
        position state). The dict is merged into ``algo_state.state`` in Postgres
        after every candle. Default implementation returns an empty dict.
        """
        return {}

    @abstractmethod
    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        """
        Called on every completed candle.

        Parameters
        ----------
        symbol:
            Instrument trading symbol (e.g. "INFY").
        instrument_type:
            Equity, futures, options, etc.
        df:
            Rolling OHLCV DataFrame enriched with technical indicators
            (ema_9, ema_21, rsi_14, atr_14, vwap). Strategies should call
            ``df.tail(n)`` as needed rather than assuming a fixed length.

        Returns
        -------
        Signal
            A trading signal, or ``None`` if no action should be taken.
        """
