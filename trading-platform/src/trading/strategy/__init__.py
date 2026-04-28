"""
Strategy plugin system.

Public API
----------
    from trading.strategy import Strategy, Signal, strategy

    # Look up a registered strategy class by alias
    cls = Strategy.get("ema_crossover")

    # Instantiate directly
    inst = Strategy.create("ema_crossover", fast=5, slow=13)

    # Register via decorator (alternative to class-level alias attribute)
    @strategy("my_strategy")
    class MyStrategy(Strategy):
        ...

    # Trigger discovery of all modules in a package
    Strategy.discover("my_app.strategies")

    # Inspect the full registry
    print(Strategy.registered())

Built-in strategies (auto-discovered on first use):
    "ema_crossover"          EmaCrossoverStrategy
    "rsi_mean_reversion"     RsiMeanReversionStrategy
    "vwap_reversion"         VwapReversionStrategy
    "opening_range_breakout" OpeningRangeBreakoutStrategy
"""

from trading.strategy.base import Signal, Strategy
from trading.strategy.decorators import strategy

__all__ = ["Signal", "Strategy", "strategy"]
