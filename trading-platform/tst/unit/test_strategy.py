"""Tests for strategy/base.py and strategy/examples/ema_crossover.py"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import polars as pl
import pytest

from trading.core.schemas import InstrumentType, Side, SignalType
from trading.strategy.ema_crossover import EmaCrossoverStrategy

BASE_TIME = datetime(2025, 1, 6, 3, 45, 0, tzinfo=UTC)


def make_df(rows: list[dict]) -> pl.DataFrame:
    """Build a minimal DataFrame with required columns."""
    n = len(rows)
    base = {
        "timestamp": [BASE_TIME + timedelta(minutes=i) for i in range(n)],
        "open": [r.get("open", 100.0) for r in rows],
        "high": [r.get("high", 105.0) for r in rows],
        "low": [r.get("low", 95.0) for r in rows],
        "close": [r.get("close", 100.0) for r in rows],
        "volume": [r.get("volume", 1000) for r in rows],
        "ema_9": [r.get("ema_9") for r in rows],
        "ema_21": [r.get("ema_21") for r in rows],
        "atr_14": [r.get("atr_14") for r in rows],
        "rsi_14": [r.get("rsi_14") for r in rows],
        "vwap": [r.get("vwap") for r in rows],
    }
    return pl.DataFrame(base)


strategy = EmaCrossoverStrategy()
INFY = "INFY"
EQUITY = InstrumentType.EQUITY


# ---------------------------------------------------------------------------
# BUY crossover
# ---------------------------------------------------------------------------


def test_buy_signal_on_ema9_crossing_above_ema21() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 5.0},  # ema_9 below
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},  # ema_9 above → BUY
        ]
    )
    signal = strategy.on_candle(INFY, EQUITY, df)
    assert signal is not None
    assert signal.side == Side.BUY
    assert signal.signal_type == SignalType.ENTRY
    assert signal.symbol == INFY
    assert signal.strategy_id == "ema_crossover"


def test_buy_signal_stop_distance_is_atr_times_multiplier() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 4.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 4.0},
        ]
    )
    signal = strategy.on_candle(INFY, EQUITY, df)
    assert signal is not None
    assert signal.stop_distance == pytest.approx(1.5 * 4.0)


# ---------------------------------------------------------------------------
# SELL crossover
# ---------------------------------------------------------------------------


def test_sell_signal_on_ema9_crossing_below_ema21() -> None:
    df = make_df(
        [
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},  # ema_9 above
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 5.0},  # ema_9 below → SELL
        ]
    )
    signal = strategy.on_candle(INFY, EQUITY, df)
    assert signal is not None
    assert signal.side == Side.SELL


# ---------------------------------------------------------------------------
# No signal cases
# ---------------------------------------------------------------------------


def test_no_signal_when_no_crossover_ema9_above() -> None:
    df = make_df(
        [
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 103.0, "ema_21": 100.0, "atr_14": 5.0},  # still above
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_no_crossover_ema9_below() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 97.0, "ema_21": 100.0, "atr_14": 5.0},  # still below
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_with_single_row() -> None:
    df = make_df([{"ema_9": 100.0, "ema_21": 99.0, "atr_14": 5.0}])
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_ema9_null() -> None:
    df = make_df(
        [
            {"ema_9": None, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_ema21_null() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": None, "atr_14": 5.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_atr_null() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": None},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": None},
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_atr_zero() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 0.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 0.0},
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


def test_no_signal_when_emas_equal() -> None:
    """Equal EMAs do not constitute a crossover."""
    df = make_df(
        [
            {"ema_9": 100.0, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 100.0, "ema_21": 100.0, "atr_14": 5.0},
        ]
    )
    assert strategy.on_candle(INFY, EQUITY, df) is None


# ---------------------------------------------------------------------------
# Signal properties
# ---------------------------------------------------------------------------


def test_each_signal_has_unique_signal_id() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},
        ]
    )
    s1 = strategy.on_candle(INFY, EQUITY, df)
    s2 = strategy.on_candle(INFY, EQUITY, df)
    assert s1 is not None and s2 is not None
    assert s1.signal_id != s2.signal_id


def test_signal_id_is_valid_uuid() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 5.0},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 5.0},
        ]
    )
    signal = strategy.on_candle(INFY, EQUITY, df)
    assert signal is not None
    assert isinstance(signal.signal_id, UUID)
    assert signal.signal_id.version == 4


def test_signal_stop_distance_always_positive() -> None:
    df = make_df(
        [
            {"ema_9": 98.0, "ema_21": 100.0, "atr_14": 2.5},
            {"ema_9": 102.0, "ema_21": 100.0, "atr_14": 2.5},
        ]
    )
    signal = strategy.on_candle(INFY, EQUITY, df)
    assert signal is not None
    assert signal.stop_distance > 0
