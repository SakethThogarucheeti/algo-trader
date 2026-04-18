from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AlgoConfig:
    """
    Runtime configuration for one trading algo.

    Assembled by the DI provider from ``AlgoSettings`` (the Pydantic model
    loaded from the ALGOS env var). This dataclass carries the resolved string
    IDs that the provider's factory functions use to construct concrete
    component instances (Strategy, FeatureEngine, RiskController, etc.).

    Attributes
    ----------
    name:
        Unique identifier for this algo. Used to scope Redis channels:
        ``signals:{name}`` and ``validated_orders:{name}``.
    instruments:
        Trading symbol strings (e.g. ["INFY", "TCS"]) that this algo watches.
    broker_name:
        "zerodha" | "paper" — resolved by the DI provider to a Broker instance.
    strategy_id:
        Key passed to ``_make_strategy()`` factory in the DI provider.
    risk_controller_id:
        Key passed to ``_make_risk_controller()`` factory.
    feature_engine_id:
        Key passed to ``_make_feature_engine()`` factory.
    execution_engine_id:
        Key passed to ``_make_execution_engine()`` factory.
    candle_intervals:
        Overrides global ``Settings.candle_intervals`` for this algo.
        ``None`` means use the global default.
    equity:
        Capital allocated to this algo for risk sizing (position sizer input).
    """

    name: str
    instruments: list[str]
    broker_name: str = "zerodha"
    strategy_id: str = "ema_crossover"
    risk_controller_id: str = "default"
    feature_engine_id: str = "technical"
    execution_engine_id: str = "direct"
    candle_intervals: list[str] | None = None
    equity: float = 100_000.0
