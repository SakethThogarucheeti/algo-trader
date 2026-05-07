from __future__ import annotations

import inspect
from typing import Any

from trading.core.clock import Clock
from trading.strategy.base import Strategy
from trading.strategy.ema_crossover import EmaCrossoverStrategy
from trading.strategy.opening_range_breakout import OpeningRangeBreakoutStrategy
from trading.strategy.rsi_mean_reversion import RsiMeanReversionStrategy
from trading.strategy.vwap_reversion import VwapReversionStrategy

_STRATEGIES: dict[str, type[Strategy]] = {
    "ema_crossover": EmaCrossoverStrategy,
    "rsi_mean_reversion": RsiMeanReversionStrategy,
    "opening_range_breakout": OpeningRangeBreakoutStrategy,
    "vwap_reversion": VwapReversionStrategy,
}


class StrategyFactory:
    """Maps strategy IDs to their classes and instantiates them with runtime deps."""

    @staticmethod
    def get(strategy_id: str) -> type[Strategy]:
        try:
            return _STRATEGIES[strategy_id]
        except KeyError:
            available = ", ".join(sorted(_STRATEGIES))
            raise ValueError(
                f"Unknown strategy {strategy_id!r}. Available: {available}."
            ) from None

    @staticmethod
    def create(
        strategy_id: str,
        params: dict[str, Any] | None = None,
        clock: Clock | None = None,
    ) -> Strategy:
        cls = StrategyFactory.get(strategy_id)
        kwargs = dict(params or {})
        if clock is not None and "clock" in inspect.signature(cls.__init__).parameters:
            kwargs["clock"] = clock
        return cls(**kwargs)

    @staticmethod
    def registered() -> dict[str, type[Strategy]]:
        return dict(_STRATEGIES)
