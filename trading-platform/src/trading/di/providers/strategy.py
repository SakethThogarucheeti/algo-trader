from __future__ import annotations

from trading.strategy.base import Strategy
from trading.strategy.examples.ema_crossover import EmaCrossoverStrategy


def make_strategy(strategy_id: str) -> Strategy:
    """Resolve a strategy_id string to a Strategy instance.

    To add a new strategy: add a case here and a class file under
    trading/strategy/. No registry dict to maintain.
    """
    match strategy_id:
        case "ema_crossover":
            return EmaCrossoverStrategy()
        case _:
            raise ValueError(
                f"Unknown strategy_id: {strategy_id!r}. "
                f"Add a case to make_strategy() in di/providers/strategy.py."
            )
