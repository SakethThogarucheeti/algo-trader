from __future__ import annotations

from typing import Any

from trading.features.base import FeatureEngine
from trading.features.technical import TechnicalFeatureEngine


def make_feature_engine(engine_id: str, params: dict[str, Any] | None = None) -> FeatureEngine:
    """Resolve a feature_engine_id string to a FeatureEngine instance.

    Parameters
    ----------
    engine_id:
        Registered feature engine identifier.
    params:
        Optional keyword arguments forwarded to the engine constructor.
        Use this for hyperparameter tuning (e.g. ``{"ema_spans": (5, 13), "atr_period": 10}``).

    To add a new feature engine: add a case here and a class file under
    trading/features/. No registry dict to maintain.
    """
    kwargs: dict[str, Any] = params or {}
    match engine_id:
        case "technical":
            return TechnicalFeatureEngine(**kwargs)
        case _:
            raise ValueError(
                f"Unknown feature_engine_id: {engine_id!r}. "
                f"Add a case to make_feature_engine() in di/providers/features.py."
            )
