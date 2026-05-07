"""
Strategy package.

Public API
----------
    from trading.strategy import Strategy, Signal, StrategyFactory

    # Look up a strategy class by ID
    cls = StrategyFactory.get("ema_crossover")

    # Instantiate with optional params and clock
    inst = StrategyFactory.create("ema_crossover", params={"fast": 5, "slow": 13})

    # Inspect all registered strategies
    print(StrategyFactory.registered())

Built-in strategies:
    "ema_crossover"          EmaCrossoverStrategy
    "rsi_mean_reversion"     RsiMeanReversionStrategy
    "vwap_reversion"         VwapReversionStrategy
    "opening_range_breakout" OpeningRangeBreakoutStrategy
"""

from trading.strategy.base import Signal, Strategy
from trading.strategy.factory import StrategyFactory

__all__ = ["Signal", "Strategy", "StrategyFactory"]
