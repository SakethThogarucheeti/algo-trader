"""
Tests for the FeatureEngine plugin registry.

Covers registration, factory, discovery, and duplicate detection.
Structure mirrors test_registry.py — the registry mechanism is identical.
"""

from __future__ import annotations

import polars as pl
import pytest

from trading.core.schemas import CandleEvent
from trading.features.base import FeatureEngine, _REGISTRY, _discovered

# Eager import so __init_subclass__ fires and the built-in is in _REGISTRY
# before any fixture snapshots it.
import trading.features.technical  # noqa: F401, E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=False)
def clean_registry():
    """Snapshot registry + discovery state; restore after each test."""
    import trading.features.base as _base
    before = dict(_REGISTRY)
    before_discovered = set(_discovered)
    before_default = _base._default_discovered
    yield
    _REGISTRY.clear()
    _REGISTRY.update(before)
    _discovered.clear()
    _discovered.update(before_discovered)
    _base._default_discovered = before_default


# ── Helpers ────────────────────────────────────────────────────────────────────

def _noop_engine(alias: str) -> type[FeatureEngine]:
    class _Impl(FeatureEngine):
        def update(self, event: CandleEvent) -> pl.DataFrame:
            return pl.DataFrame()
        def get(self, symbol: str, interval: str) -> pl.DataFrame | None:
            return None
    _Impl.__name__ = f"Engine_{alias}"
    _Impl.__qualname__ = _Impl.__name__
    _Impl.alias = alias  # type: ignore[attr-defined]
    _REGISTRY[alias] = _Impl
    return _Impl


# ── Registration ──────────────────────────────────────────────────────────────

class TestAutoRegistration:
    def test_alias_registers_class(self, clean_registry):
        class MyEngine(FeatureEngine):
            alias = "my_engine"
            def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
            def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

        assert "my_engine" in _REGISTRY
        assert _REGISTRY["my_engine"] is MyEngine

    def test_no_alias_not_registered(self, clean_registry):
        class IntermediateEngine(FeatureEngine):
            def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
            def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

        assert "alias" not in IntermediateEngine.__dict__

    def test_duplicate_alias_raises(self, clean_registry):
        class First(FeatureEngine):
            alias = "dup_engine"
            def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
            def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

        with pytest.raises(ValueError, match="Duplicate FeatureEngine alias"):
            class Second(FeatureEngine):
                alias = "dup_engine"
                def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
                def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

    def test_empty_alias_raises(self, clean_registry):
        with pytest.raises(TypeError, match="non-empty string"):
            class Bad(FeatureEngine):
                alias = ""
                def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
                def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

    def test_non_string_alias_raises(self, clean_registry):
        with pytest.raises(TypeError, match="non-empty string"):
            class BadType(FeatureEngine):
                alias = 99  # type: ignore[assignment]
                def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
                def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None


# ── Factory ───────────────────────────────────────────────────────────────────

class TestFactory:
    def test_get_returns_class(self, clean_registry):
        _noop_engine("get_test")
        assert FeatureEngine.lookup("get_test") is _REGISTRY["get_test"]

    def test_get_unknown_raises(self, clean_registry):
        with pytest.raises(ValueError, match="Unknown FeatureEngine alias"):
            FeatureEngine.lookup("does_not_exist_xyz")

    def test_create_returns_instance(self, clean_registry):
        cls = _noop_engine("create_test")
        inst = FeatureEngine.create("create_test")
        assert isinstance(inst, cls)

    def test_create_forwards_kwargs(self, clean_registry):
        class ParamEngine(FeatureEngine):
            alias = "param_engine"
            def __init__(self, window: int = 50) -> None:
                self.window = window
            def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
            def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

        inst = FeatureEngine.create("param_engine", window=100)
        assert inst.window == 100

    def test_registered_returns_snapshot(self, clean_registry):
        _noop_engine("snap_engine")
        reg = FeatureEngine.registered()
        assert "snap_engine" in reg
        assert reg is not _REGISTRY  # must be a copy

    def test_id_property_returns_alias(self, clean_registry):
        class IdEngine(FeatureEngine):
            alias = "id_engine"
            def update(self, event: CandleEvent) -> pl.DataFrame: return pl.DataFrame()
            def get(self, symbol: str, interval: str) -> pl.DataFrame | None: return None

        inst = IdEngine()
        assert inst.id == "id_engine"


# ── Built-in: TechnicalFeatureEngine ─────────────────────────────────────────

class TestTechnicalEngine:
    """Smoke-tests for the built-in TechnicalFeatureEngine."""

    @classmethod
    def setup_class(cls):
        import trading.features.technical  # noqa: F401

    def test_registered(self):
        assert "technical" in FeatureEngine.registered()

    def test_create_default(self):
        inst = FeatureEngine.create("technical")
        assert isinstance(inst, FeatureEngine)
        assert inst.id == "technical"

    def test_create_with_params(self):
        inst = FeatureEngine.create("technical", ema_spans=(5, 10), atr_period=7)
        from trading.features.technical import TechnicalFeatureEngine
        assert isinstance(inst, TechnicalFeatureEngine)
        assert inst._ema_spans == (5, 10)  # type: ignore[attr-defined]
        assert inst._atr_period == 7  # type: ignore[attr-defined]

    def test_unknown_alias_raises(self):
        with pytest.raises(ValueError, match="Unknown FeatureEngine alias"):
            FeatureEngine.create("nonexistent_engine")
