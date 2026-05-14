"""Tests for indicators/base.py — registry and alias guard."""

from __future__ import annotations

import pytest

from trading.indicators.base import Indicator


def test_indicator_aliases_registered() -> None:
    import trading.indicators  # noqa: F401
    from trading.indicators.base import _REGISTRY

    for alias in (
        "ema",
        "sma",
        "rsi",
        "atr",
        "vwap",
        "wilder_ema",
        "true_range",
        "macd",
        "bollinger",
        "stochastic",
        "cci",
        "williams_r",
        "roc",
        "momentum",
        "donchian",
        "keltner",
        "hv",
        "obv",
        "mfi",
        "cmf",
        "vwma",
        "pivot",
        "supertrend",
        "psar",
        "adx",
        "chaikin_vol",
    ):
        assert alias in _REGISTRY, f"alias {alias!r} not registered"


def test_duplicate_alias_raises() -> None:
    with pytest.raises(ValueError, match="Duplicate Indicator alias"):

        class _DupEMA(Indicator):
            alias = "ema"

            async def compute(self, params): ...  # type: ignore[override]


def test_missing_alias_is_allowed_for_abstract_intermediates() -> None:
    class _AbstractMid(Indicator):
        async def compute(self, params): ...  # type: ignore[override]

    # No alias → no registration, no error
    from trading.indicators.base import _REGISTRY

    assert _AbstractMid not in _REGISTRY.values()


def test_empty_alias_raises() -> None:
    with pytest.raises(TypeError, match="alias must be a non-empty string"):

        class _Bad(Indicator):
            alias = ""

            async def compute(self, params): ...  # type: ignore[override]
