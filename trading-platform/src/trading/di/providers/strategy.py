from __future__ import annotations

from typing import Any

from trading.strategy.base import Strategy
from trading.strategy.examples.ema_crossover import EmaCrossoverStrategy
from trading.strategy.examples.opening_range_breakout import OpeningRangeBreakoutStrategy
from trading.strategy.examples.rsi_mean_reversion import RsiMeanReversionStrategy
from trading.strategy.examples.vwap_reversion import VwapReversionStrategy


def make_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> Strategy:
    """Resolve a strategy_id string to a Strategy instance.

    Parameters
    ----------
    strategy_id:
        Registered strategy identifier.
    params:
        Optional keyword arguments forwarded to the strategy constructor.
        Use this for hyperparameter tuning (e.g. ``{"fast": 5, "slow": 13}``).

    To add a new strategy: add a case here and a class file under
    trading/strategy/. No registry dict to maintain.
    """
    kwargs: dict[str, Any] = params or {}
    match strategy_id:
        case "ema_crossover":
            return EmaCrossoverStrategy(**kwargs)
        case "rsi_mean_reversion":
            return RsiMeanReversionStrategy(**kwargs)
        case "vwap_reversion":
            return VwapReversionStrategy(**kwargs)
        case "opening_range_breakout":
            return OpeningRangeBreakoutStrategy(**kwargs)
        case _:
            raise ValueError(
                f"Unknown strategy_id: {strategy_id!r}. "
                f"Add a case to make_strategy() in di/providers/strategy.py."
            )
