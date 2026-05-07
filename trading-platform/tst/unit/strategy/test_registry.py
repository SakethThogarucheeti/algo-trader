"""
Tests for StrategyFactory.

Covers:
- get() returns correct class
- get() raises on unknown alias
- create() returns correct instance with no params
- create() forwards params to constructor
- create() injects clock for strategies that accept it
- create() does not inject clock for strategies that don't
- registered() returns all built-in entries
- id property delegates to class alias
- EmaCrossoverStrategy rejects fast >= slow
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from trading.core.clock import Clock
from trading.strategy.base import Signal, Strategy
from trading.strategy.ema_crossover import EmaCrossoverStrategy
from trading.strategy.factory import StrategyFactory
from trading.strategy.opening_range_breakout import OpeningRangeBreakoutStrategy
from trading.strategy.rsi_mean_reversion import RsiMeanReversionStrategy
from trading.strategy.vwap_reversion import VwapReversionStrategy

_BUILTIN_ALIASES = [
    "ema_crossover",
    "rsi_mean_reversion",
    "vwap_reversion",
    "opening_range_breakout",
]


class TestGet:
    @pytest.mark.parametrize("alias,expected_cls", [
        ("ema_crossover", EmaCrossoverStrategy),
        ("rsi_mean_reversion", RsiMeanReversionStrategy),
        ("vwap_reversion", VwapReversionStrategy),
        ("opening_range_breakout", OpeningRangeBreakoutStrategy),
    ])
    def test_returns_correct_class(self, alias, expected_cls):
        assert StrategyFactory.get(alias) is expected_cls

    def test_unknown_alias_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            StrategyFactory.get("does_not_exist")

    def test_error_message_lists_available(self):
        with pytest.raises(ValueError, match="ema_crossover"):
            StrategyFactory.get("nope")


class TestCreate:
    @pytest.mark.parametrize("alias", _BUILTIN_ALIASES)
    def test_create_no_params_returns_strategy_instance(self, alias):
        inst = StrategyFactory.create(alias)
        assert isinstance(inst, Strategy)

    def test_create_forwards_params(self):
        inst = StrategyFactory.create("ema_crossover", params={"fast": 5, "slow": 20})
        assert isinstance(inst, EmaCrossoverStrategy)
        assert inst._fast_period == 5
        assert inst._slow_period == 20

    def test_create_injects_clock_when_strategy_accepts_it(self):
        clock = MagicMock(spec=Clock)
        inst = StrategyFactory.create("vwap_reversion", clock=clock)
        assert isinstance(inst, VwapReversionStrategy)
        assert inst._clock is clock

    def test_create_does_not_inject_clock_for_strategies_that_dont_accept_it(self):
        clock = MagicMock(spec=Clock)
        # Should not raise even though ema_crossover has no clock param
        inst = StrategyFactory.create("ema_crossover", clock=clock)
        assert isinstance(inst, EmaCrossoverStrategy)

    def test_create_unknown_alias_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            StrategyFactory.create("nonexistent")

    def test_create_none_params_is_same_as_empty(self):
        inst1 = StrategyFactory.create("rsi_mean_reversion", params=None)
        inst2 = StrategyFactory.create("rsi_mean_reversion", params={})
        assert type(inst1) is type(inst2)


class TestRegistered:
    def test_all_builtins_present(self):
        reg = StrategyFactory.registered()
        for alias in _BUILTIN_ALIASES:
            assert alias in reg

    def test_returns_copy(self):
        reg = StrategyFactory.registered()
        reg["injected"] = object()  # type: ignore[assignment]
        assert "injected" not in StrategyFactory.registered()


class TestIdProperty:
    @pytest.mark.parametrize("alias,cls", [
        ("ema_crossover", EmaCrossoverStrategy),
        ("rsi_mean_reversion", RsiMeanReversionStrategy),
    ])
    def test_id_returns_alias(self, alias, cls):
        inst = cls()
        assert inst.id == alias


class TestEmaCrossoverValidation:
    def test_fast_ge_slow_raises(self):
        with pytest.raises(ValueError, match="fast"):
            EmaCrossoverStrategy(fast=21, slow=9)

    def test_fast_equal_slow_raises(self):
        with pytest.raises(ValueError, match="fast"):
            EmaCrossoverStrategy(fast=14, slow=14)
