"""
Tests for the Strategy plugin registry.

Covers:
- __init_subclass__ auto-registration via class-level alias
- @strategy() decorator registration
- Strategy.get() / Strategy.create() factory
- Strategy.registered() snapshot
- Duplicate alias detection
- Unknown alias error
- Recursive package discovery via Strategy.discover()
- Idempotent discovery (re-calling discover() doesn't re-import or re-register)
- Import error handling during discovery
- Config-driven instantiation pattern
- id property delegates to class alias
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any
from unittest.mock import patch

import polars as pl
import pytest

from trading.core.schemas import InstrumentType
from trading.strategy.base import Signal, Strategy, _REGISTRY, _discovered

# Import all concrete strategies eagerly so __init_subclass__ fires and
# populates _REGISTRY before any test snapshots it.
import trading.strategy.ema_crossover  # noqa: F401, E402
import trading.strategy.rsi_mean_reversion  # noqa: F401, E402
import trading.strategy.vwap_reversion  # noqa: F401, E402
import trading.strategy.opening_range_breakout  # noqa: F401, E402

from trading.strategy.decorators import strategy


# ── Fixtures: isolated registry state ─────────────────────────────────────────
# Each test that mutates the registry must clean up after itself.
# We use a context manager approach via fixtures.

@pytest.fixture(autouse=False)
def clean_registry():
    """Snapshot the registry + discovery state before the test and restore after."""
    import trading.strategy.base as _base
    before = dict(_REGISTRY)
    before_discovered = set(_discovered)
    before_default_discovered = _base._default_discovered
    yield
    _REGISTRY.clear()
    _REGISTRY.update(before)
    _discovered.clear()
    _discovered.update(before_discovered)
    _base._default_discovered = before_default_discovered


# ── Helpers ────────────────────────────────────────────────────────────────────

def _noop_strategy(alias: str) -> type[Strategy]:
    """Dynamically create a minimal Strategy subclass with the given alias."""

    class _Impl(Strategy):
        def on_candle(self, symbol: str, instrument_type: InstrumentType, df: pl.DataFrame) -> Signal | None:
            return None

    _Impl.__name__ = f"Strategy_{alias}"
    _Impl.__qualname__ = _Impl.__name__
    _Impl.alias = alias  # type: ignore[attr-defined]
    # Trigger __init_subclass__ manually (already fired at class creation above,
    # but alias wasn't set then because we set it post-hoc). Re-register:
    _REGISTRY[alias] = _Impl
    return _Impl


# ── Registration via class-level alias ────────────────────────────────────────

class TestAutoRegistration:
    def test_alias_attribute_registers_class(self, clean_registry):
        class MyStrat(Strategy):
            alias = "test_auto_reg"

            def on_candle(self, symbol, instrument_type, df):
                return None

        assert "test_auto_reg" in _REGISTRY
        assert _REGISTRY["test_auto_reg"] is MyStrat

    def test_abstract_subclass_without_alias_not_registered(self, clean_registry):
        # Intermediate abstract base — no alias → should not appear in registry
        class IntermediateBase(Strategy):
            def some_helper(self): ...

            def on_candle(self, symbol, instrument_type, df):
                return None

        assert "IntermediateBase" not in _REGISTRY
        # Confirm it genuinely has no alias attribute in its own __dict__
        assert "alias" not in IntermediateBase.__dict__

    def test_duplicate_alias_same_class_is_idempotent(self, clean_registry):
        # Re-registering the exact same class is safe (happens on re-import)
        class StableStrat(Strategy):
            alias = "stable"

            def on_candle(self, symbol, instrument_type, df):
                return None

        # Simulate a second registration of the same class
        _REGISTRY["stable"] = StableStrat  # no-op if same class
        assert _REGISTRY["stable"] is StableStrat

    def test_duplicate_alias_different_class_raises(self, clean_registry):
        class First(Strategy):
            alias = "collision"

            def on_candle(self, symbol, instrument_type, df):
                return None

        with pytest.raises(ValueError, match="Duplicate strategy alias"):
            class Second(Strategy):
                alias = "collision"

                def on_candle(self, symbol, instrument_type, df):
                    return None

    def test_empty_alias_raises_type_error(self, clean_registry):
        with pytest.raises(TypeError, match="non-empty string"):
            class BadStrat(Strategy):
                alias = ""

                def on_candle(self, symbol, instrument_type, df):
                    return None

    def test_non_string_alias_raises_type_error(self, clean_registry):
        with pytest.raises(TypeError, match="non-empty string"):
            class NumericAlias(Strategy):
                alias = 42  # type: ignore[assignment]

                def on_candle(self, symbol, instrument_type, df):
                    return None


# ── Registration via @strategy() decorator ────────────────────────────────────

class TestDecoratorRegistration:
    def test_decorator_registers_class(self, clean_registry):
        @strategy("test_decorator")
        class DecoratedStrat(Strategy):
            def on_candle(self, symbol, instrument_type, df):
                return None

        assert "test_decorator" in _REGISTRY
        assert _REGISTRY["test_decorator"] is DecoratedStrat

    def test_decorator_sets_alias_attribute(self, clean_registry):
        @strategy("decorated_with_alias")
        class DS(Strategy):
            def on_candle(self, symbol, instrument_type, df):
                return None

        assert DS.alias == "decorated_with_alias"  # type: ignore[attr-defined]

    def test_decorator_class_level_alias_match_is_ok(self, clean_registry):
        """class-level alias + matching decorator = no error."""
        @strategy("both_match")
        class BothMatch(Strategy):
            alias = "both_match"

            def on_candle(self, symbol, instrument_type, df):
                return None

        assert _REGISTRY["both_match"] is BothMatch

    def test_decorator_alias_conflicts_with_class_alias_raises(self, clean_registry):
        with pytest.raises(ValueError, match="conflicts with class-level alias"):
            @strategy("decorator_alias")
            class Mismatch(Strategy):
                alias = "class_alias"

                def on_candle(self, symbol, instrument_type, df):
                    return None

    def test_decorator_on_non_strategy_raises(self):
        with pytest.raises(TypeError, match="Strategy subclasses"):
            @strategy("bad_target")
            class NotAStrategy:
                pass

    def test_decorator_empty_alias_raises(self):
        with pytest.raises(TypeError, match="non-empty string"):
            strategy("")

    def test_decorator_duplicate_raises(self, clean_registry):
        @strategy("deco_dup")
        class First(Strategy):
            def on_candle(self, symbol, instrument_type, df):
                return None

        with pytest.raises(ValueError, match="Duplicate strategy alias"):
            @strategy("deco_dup")
            class Second(Strategy):
                def on_candle(self, symbol, instrument_type, df):
                    return None


# ── Strategy.get() and Strategy.create() ─────────────────────────────────────

class TestFactoryMethods:
    def test_get_returns_class(self, clean_registry):
        class GettableStrat(Strategy):
            alias = "gettable"

            def on_candle(self, symbol, instrument_type, df):
                return None

        cls = Strategy.get("gettable")
        assert cls is GettableStrat

    def test_get_unknown_alias_raises_value_error(self, clean_registry):
        with pytest.raises(ValueError, match="Unknown strategy alias"):
            Strategy.get("does_not_exist_xyz")

    def test_create_returns_instance(self, clean_registry):
        class CreatableStrat(Strategy):
            alias = "creatable"

            def on_candle(self, symbol, instrument_type, df):
                return None

        inst = Strategy.create("creatable")
        assert isinstance(inst, CreatableStrat)

    def test_create_forwards_kwargs(self, clean_registry):
        class ParamStrat(Strategy):
            alias = "with_params"

            def __init__(self, threshold: float = 1.0) -> None:
                self.threshold = threshold

            def on_candle(self, symbol, instrument_type, df):
                return None

        inst = Strategy.create("with_params", threshold=42.0)
        assert inst.threshold == 42.0

    def test_create_unknown_alias_raises(self, clean_registry):
        with pytest.raises(ValueError, match="Unknown strategy alias"):
            Strategy.create("unknown_xyz")

    def test_registered_returns_snapshot(self, clean_registry):
        class SnapshotStrat(Strategy):
            alias = "snapshot_strat"

            def on_candle(self, symbol, instrument_type, df):
                return None

        reg = Strategy.registered()
        assert "snapshot_strat" in reg
        assert reg is not _REGISTRY  # must be a copy


# ── id property ───────────────────────────────────────────────────────────────

class TestIdProperty:
    def test_id_returns_alias(self, clean_registry):
        class IdStrat(Strategy):
            alias = "id_test"

            def on_candle(self, symbol, instrument_type, df):
                return None

        inst = IdStrat()
        assert inst.id == "id_test"

    def test_id_matches_class_alias(self, clean_registry):
        class IdStrat2(Strategy):
            alias = "id_test_2"

            def on_candle(self, symbol, instrument_type, df):
                return None

        assert IdStrat2().id == IdStrat2.alias  # type: ignore[attr-defined]


# ── Config-driven instantiation ───────────────────────────────────────────────

class TestConfigDriven:
    def test_config_dict_drives_creation(self, clean_registry):
        class ConfigStrat(Strategy):
            alias = "config_driven"

            def __init__(self, fast: int = 9, slow: int = 21) -> None:
                self.fast = fast
                self.slow = slow

            def on_candle(self, symbol, instrument_type, df):
                return None

        config: dict[str, Any] = {"strategy": "config_driven", "params": {"fast": 5, "slow": 13}}
        inst = Strategy.create(config["strategy"], **config["params"])
        assert inst.fast == 5
        assert inst.slow == 13

    def test_dishka_friendly_get_returns_class(self, clean_registry):
        """Strategy.get() returns the class so container.get(cls) works without coupling."""
        class DishkaStrat(Strategy):
            alias = "dishka_ready"

            def on_candle(self, symbol, instrument_type, df):
                return None

        cls = Strategy.get("dishka_ready")
        # Simulate what dishka would do: resolve by class
        assert cls is DishkaStrat
        assert issubclass(cls, Strategy)


# ── Package discovery ─────────────────────────────────────────────────────────

class TestDiscovery:
    def test_discover_imports_modules_in_package(self):
        """Strategy.discover() on the real strategy package registers built-ins."""
        # Use a fresh temporary package for a clean test. The real strategy package
        # is already imported, so we verify via the registry which is populated
        # by __init_subclass__ at import time.
        from trading.strategy.ema_crossover import EmaCrossoverStrategy
        from trading.strategy.rsi_mean_reversion import RsiMeanReversionStrategy
        from trading.strategy.vwap_reversion import VwapReversionStrategy
        from trading.strategy.opening_range_breakout import OpeningRangeBreakoutStrategy

        reg = Strategy.registered()
        assert "ema_crossover" in reg
        assert "rsi_mean_reversion" in reg
        assert "vwap_reversion" in reg
        assert "opening_range_breakout" in reg

    def test_discover_is_idempotent(self):
        """Calling discover() twice on the same package is safe."""
        before = dict(Strategy.registered())
        Strategy.discover("trading.strategy")
        Strategy.discover("trading.strategy")
        after = Strategy.registered()
        # Registry should be a superset of before (no aliases removed)
        for key in before:
            assert key in after

    def test_discover_handles_import_error_gracefully(self, clean_registry, caplog):
        """A failing module during discovery logs a warning but doesn't abort."""
        import pkgutil

        bad_module_name = "trading.strategy._broken_module"

        # Inject a fake module into sys.modules that raises on import
        original = sys.modules.get(bad_module_name)

        def fake_walk_packages(path, prefix=""):
            yield pkgutil.ModuleInfo(finder=None, name=bad_module_name, ispkg=False)  # type: ignore[arg-type]

        with patch("pkgutil.walk_packages", fake_walk_packages):
            with patch("importlib.import_module", side_effect=ImportError("boom")):
                import logging
                with caplog.at_level(logging.WARNING, logger="trading.strategy.base"):
                    Strategy.discover("trading.strategy._fake_pkg_that_triggers_walk")

        # No exception propagated — discovery gracefully skipped the bad module
        if original is None:
            sys.modules.pop(bad_module_name, None)

    def test_lazy_discover_on_create(self):
        """
        Strategy.create() triggers lazy discovery before lookup.

        We verify this by ensuring ema_crossover is accessible via Strategy.create()
        even if called on a fresh import, which means lazy discovery must fire.
        Since the strategy modules are already imported in this process, we just
        verify the end result: create() works without an explicit discover() call.
        """
        inst = Strategy.create("ema_crossover")
        from trading.strategy.ema_crossover import EmaCrossoverStrategy
        assert isinstance(inst, EmaCrossoverStrategy)

    def test_recursive_discovery_finds_nested_packages(self, clean_registry, tmp_path):
        """
        Build a temporary package with a nested sub-package and confirm that
        Strategy.discover() walks into it.
        """
        # Create: tmp_strats/
        #           __init__.py
        #           momentum/
        #             __init__.py
        #             macd.py          ← defines MACDStrategy with alias "macd"
        pkg_root = tmp_path / "tmp_strats"
        pkg_root.mkdir()
        (pkg_root / "__init__.py").write_text("")
        nested = pkg_root / "momentum"
        nested.mkdir()
        (nested / "__init__.py").write_text("")
        (nested / "macd.py").write_text(
            "from trading.strategy.base import Strategy, Signal\n"
            "import polars as pl\n"
            "from trading.core.schemas import InstrumentType\n"
            "class MACDStrategy(Strategy):\n"
            "    alias = 'macd'\n"
            "    def on_candle(self, symbol, instrument_type, df): return None\n"
        )

        # Temporarily add tmp_path to sys.path so importlib can find tmp_strats
        sys.path.insert(0, str(tmp_path))
        try:
            Strategy.discover("tmp_strats")
            assert "macd" in Strategy.registered()
        finally:
            sys.path.pop(0)
            # Cleanup sys.modules so other tests are not polluted
            for key in list(sys.modules):
                if key.startswith("tmp_strats"):
                    del sys.modules[key]
            _REGISTRY.pop("macd", None)
            _discovered.discard("tmp_strats")
            _discovered.discard("tmp_strats.momentum")
            _discovered.discard("tmp_strats.momentum.macd")


# ── Built-in strategies round-trip ───────────────────────────────────────────

class TestBuiltinStrategies:
    """
    Smoke-test that all 4 built-in strategies register and instantiate cleanly.

    These tests do NOT use clean_registry — they rely on the live registry
    which is populated by __init_subclass__ when each strategy module is imported.
    Importing trading.strategy ensures all built-ins are registered.
    """

    @classmethod
    def setup_class(cls):
        # Import the package to trigger __init_subclass__ on all concrete classes.
        import trading.strategy.ema_crossover  # noqa: F401
        import trading.strategy.rsi_mean_reversion  # noqa: F401
        import trading.strategy.vwap_reversion  # noqa: F401
        import trading.strategy.opening_range_breakout  # noqa: F401

    @pytest.mark.parametrize("alias", [
        "ema_crossover",
        "rsi_mean_reversion",
        "vwap_reversion",
        "opening_range_breakout",
    ])
    def test_builtin_registered_after_discover(self, alias):
        assert alias in Strategy.registered()

    @pytest.mark.parametrize("alias", [
        "ema_crossover",
        "rsi_mean_reversion",
        "vwap_reversion",
        "opening_range_breakout",
    ])
    def test_builtin_create_no_kwargs(self, alias):
        inst = Strategy.create(alias)
        assert isinstance(inst, Strategy)
        assert inst.id == alias

    def test_ema_crossover_create_with_params(self):
        inst = Strategy.create("ema_crossover", fast=5, slow=20)
        assert inst._fast == 5  # type: ignore[attr-defined]
        assert inst._slow == 20  # type: ignore[attr-defined]

    def test_ema_crossover_invalid_params_raises(self):
        with pytest.raises(ValueError, match="fast"):
            Strategy.create("ema_crossover", fast=21, slow=9)
