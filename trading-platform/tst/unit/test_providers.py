"""Tests for di/providers — factory functions: make_strategy, make_feature_engine"""

from __future__ import annotations

import pytest

from trading.di.providers.features import make_feature_engine
from trading.di.providers.strategy import make_strategy
from trading.features.technical import TechnicalFeatureEngine
from trading.strategy.ema_crossover import EmaCrossoverStrategy
from trading.strategy.opening_range_breakout import OpeningRangeBreakoutStrategy
from trading.strategy.rsi_mean_reversion import RsiMeanReversionStrategy
from trading.strategy.vwap_reversion import VwapReversionStrategy


# ---------------------------------------------------------------------------
# make_strategy
# ---------------------------------------------------------------------------


def test_make_strategy_ema_crossover() -> None:
    s = make_strategy("ema_crossover")
    assert isinstance(s, EmaCrossoverStrategy)


def test_make_strategy_rsi_mean_reversion() -> None:
    s = make_strategy("rsi_mean_reversion")
    assert isinstance(s, RsiMeanReversionStrategy)


def test_make_strategy_vwap_reversion() -> None:
    s = make_strategy("vwap_reversion")
    assert isinstance(s, VwapReversionStrategy)


def test_make_strategy_opening_range_breakout() -> None:
    s = make_strategy("opening_range_breakout")
    assert isinstance(s, OpeningRangeBreakoutStrategy)


def test_make_strategy_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown strategy alias"):
        make_strategy("nonexistent_strategy")


def test_make_strategy_passes_params() -> None:
    s = make_strategy("ema_crossover", params={"fast": 5, "slow": 13})
    assert isinstance(s, EmaCrossoverStrategy)


# ---------------------------------------------------------------------------
# make_feature_engine
# ---------------------------------------------------------------------------


def test_make_feature_engine_technical() -> None:
    fe = make_feature_engine("technical")
    assert isinstance(fe, TechnicalFeatureEngine)


def test_make_feature_engine_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown FeatureEngine alias"):
        make_feature_engine("nonexistent_engine")


def test_make_feature_engine_passes_params() -> None:
    fe = make_feature_engine("technical", params={"ema_spans": (5, 13)})
    assert isinstance(fe, TechnicalFeatureEngine)
