from __future__ import annotations

from typing import Any

from trading.features.base import FeatureEngine


def make_feature_engine(engine_id: str, params: dict[str, Any] | None = None) -> FeatureEngine:
    """
    Instantiate the feature engine registered under *engine_id*.

    Parameters
    ----------
    engine_id:
        Alias registered on the FeatureEngine subclass (e.g. ``"technical"``).
    params:
        Optional keyword arguments forwarded to the engine constructor.

    To add a new feature engine: create a module under ``trading/features/``,
    subclass ``FeatureEngine``, and set a class-level ``alias`` attribute.
    No changes here needed — the registry discovers it automatically.
    """
    return FeatureEngine.create(engine_id, **(params or {}))
