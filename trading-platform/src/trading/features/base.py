from __future__ import annotations

from abc import ABC, abstractmethod

import polars as pl

from trading.core.schemas import CandleEvent


class FeatureEngine(ABC):
    """
    Abstract base for per-(symbol, interval) feature computation.

    On each new candle, call ``update()`` to append the bar and recompute
    all indicators. Downstream consumers (strategies) call ``get()`` or use
    the returned DataFrame directly.

    Implementations are responsible for maintaining a rolling window and
    returning a complete DataFrame with all computed indicator columns.
    """

    @abstractmethod
    def update(self, event: CandleEvent) -> pl.DataFrame:
        """
        Append *event* to the rolling window and recompute all indicators.

        Returns the full updated DataFrame including OHLCV and all computed
        indicator columns. The strategy should call ``.tail(n)`` as needed.
        """

    @abstractmethod
    def get(self, symbol: str, interval: str) -> pl.DataFrame | None:
        """
        Return the current DataFrame for *(symbol, interval)* without updating.

        Returns ``None`` if no data has been ingested yet for this pair.
        """
