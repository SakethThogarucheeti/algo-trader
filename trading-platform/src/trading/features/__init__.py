"""
FeatureEngine plugin system.

Public API
----------
    from trading.features import FeatureEngine

    # Look up a registered engine class by alias
    cls = FeatureEngine.lookup("technical")

    # Instantiate directly
    inst = FeatureEngine.create("technical")
    inst = FeatureEngine.create("technical", ema_spans=(5, 13))

    # Trigger discovery of all modules in a package
    FeatureEngine.discover("my_app.features")

    # Inspect the full registry
    print(FeatureEngine.registered())

Built-in engines (auto-discovered on first use):
    "technical"    TechnicalFeatureEngine
"""

from trading.features.base import FeatureEngine

__all__ = ["FeatureEngine"]
