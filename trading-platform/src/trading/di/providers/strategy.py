from __future__ import annotations

from typing import Any

from trading.strategy.base import Strategy


def make_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> Strategy:
    """
    Instantiate the strategy registered under *strategy_id*.

    Parameters
    ----------
    strategy_id:
        Alias registered on the Strategy subclass (e.g. ``"ema_crossover"``).
    params:
        Optional keyword arguments forwarded to the strategy constructor.
        Use this for hyperparameter tuning (e.g. ``{"fast": 5, "slow": 13}``).

    To add a new strategy: create a module under ``trading/strategy/``, subclass
    ``Strategy``, and set a class-level ``alias`` attribute. No changes here needed.
    The registry discovers and imports all modules in that package automatically
    on the first call.
    """
    return Strategy.create(strategy_id, **(params or {}))
