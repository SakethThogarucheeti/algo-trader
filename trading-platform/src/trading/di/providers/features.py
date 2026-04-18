from __future__ import annotations

from trading.features.base import FeatureEngine
from trading.features.technical import TechnicalFeatureEngine


def make_feature_engine(engine_id: str) -> FeatureEngine:
    """Resolve a feature_engine_id string to a FeatureEngine instance.

    To add a new feature engine: add a case here and a class file under
    trading/features/. No registry dict to maintain.
    """
    match engine_id:
        case "technical":
            return TechnicalFeatureEngine()
        case _:
            raise ValueError(
                f"Unknown feature_engine_id: {engine_id!r}. "
                f"Add a case to make_feature_engine() in di/providers/features.py."
            )
