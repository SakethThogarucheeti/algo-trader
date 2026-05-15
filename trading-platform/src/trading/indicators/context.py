"""IndicatorContext — provides a store reference to strategies before on_candle."""

from __future__ import annotations

from trading.indicators.store import AbstractCandleStore


class IndicatorContext:
    """
    Holds the CandleStore and exposes it to strategies that need to
    construct indicators lazily on first use.

    AlgoRegistry calls ``get_store()`` to retrieve the store, which strategies
    use to construct indicator instances (each indicator takes store, symbol,
    interval in its __init__).
    """

    def __init__(self, store: AbstractCandleStore) -> None:
        self._store = store

    def get_store(self) -> AbstractCandleStore:
        return self._store
