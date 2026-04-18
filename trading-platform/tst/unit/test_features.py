"""Tests for features/technical.py — TechnicalFeatureEngine"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from trading.core.schemas import CandleEvent, InstrumentType
from trading.features.technical import TechnicalFeatureEngine

BASE_TIME = datetime(2025, 1, 6, 3, 45, 0, tzinfo=UTC)  # 09:15 IST


def make_candle(
    close: float,
    offset_minutes: int = 0,
    open: float | None = None,
    high: float | None = None,
    low: float | None = None,
    volume: int = 1000,
    symbol: str = "INFY",
    interval: str = "1min",
) -> CandleEvent:
    return CandleEvent(
        symbol=symbol,
        instrument_type=InstrumentType.EQUITY,
        interval=interval,
        open=open or close,
        high=high or close,
        low=low or close,
        close=close,
        volume=volume,
        timestamp=BASE_TIME + timedelta(minutes=offset_minutes),
        tick_log_id=0,
    )


def feed(engine: TechnicalFeatureEngine, n: int, start_price: float = 100.0) -> pl.DataFrame:
    """Feed n candles with slightly increasing prices."""
    df = pl.DataFrame()
    for i in range(n):
        df = engine.update(make_candle(close=start_price + i, offset_minutes=i))
    return df


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


def test_ema_9_defined_from_first_row() -> None:
    """ewm_mean with adjust=False returns a value from row 1 onwards (uses prior close as seed)."""
    engine = TechnicalFeatureEngine()
    df = feed(engine, 30)
    # All rows should have ema_9 (Polars ewm_mean adjust=False always emits values)
    assert df["ema_9"].null_count() == 0


def test_ema_21_defined_from_first_row() -> None:
    engine = TechnicalFeatureEngine()
    df = feed(engine, 30)
    assert df["ema_21"].null_count() == 0


def test_ema_9_tracks_price_uptrend() -> None:
    """EMA should be below the last close in a strong uptrend."""
    engine = TechnicalFeatureEngine()
    df = feed(engine, 50, start_price=100.0)
    last_close = df["close"][-1]
    last_ema9 = df["ema_9"][-1]
    # EMA lags price in an uptrend
    assert last_ema9 < last_close


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def test_rsi_always_in_range() -> None:
    engine = TechnicalFeatureEngine()
    df = feed(engine, 50)
    rsi = df["rsi_14"].drop_nulls()
    assert (rsi >= 0.0).all()
    assert (rsi <= 100.0).all()


def test_rsi_near_100_in_strong_uptrend() -> None:
    engine = TechnicalFeatureEngine()
    # Feed many strongly rising candles
    df = pl.DataFrame()
    for i in range(50):
        df = engine.update(make_candle(close=100.0 + i * 5, offset_minutes=i))
    rsi_last = df["rsi_14"][-1]
    assert rsi_last is not None and rsi_last > 70.0


def test_rsi_near_0_in_strong_downtrend() -> None:
    engine = TechnicalFeatureEngine()
    for i in range(50):
        close = max(1.0, 500.0 - i * 10)
        engine.update(make_candle(close=close, offset_minutes=i))
    df = engine.get("INFY", "1min")
    assert df is not None
    rsi_last = df["rsi_14"][-1]
    assert rsi_last is not None and rsi_last < 30.0


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------


def test_atr_always_nonnegative() -> None:
    engine = TechnicalFeatureEngine()
    for i in range(50):
        engine.update(
            make_candle(
                close=100.0 + (i % 5),
                high=105.0 + (i % 5),
                low=95.0 + (i % 5),
                offset_minutes=i,
            )
        )
    df = engine.get("INFY", "1min")
    assert df is not None
    atr = df["atr_14"].drop_nulls()
    assert (atr >= 0.0).all()


def test_atr_reflects_volatility() -> None:
    """High-volatility candles should produce larger ATR than flat candles."""
    engine_volatile = TechnicalFeatureEngine()
    engine_flat = TechnicalFeatureEngine()

    for i in range(30):
        engine_volatile.update(make_candle(close=100.0, high=115.0, low=85.0, offset_minutes=i))
        engine_flat.update(make_candle(close=100.0, high=101.0, low=99.0, offset_minutes=i))

    df_v = engine_volatile.get("INFY", "1min")
    df_f = engine_flat.get("INFY", "1min")
    assert df_v is not None and df_f is not None
    assert df_v["atr_14"][-1] > df_f["atr_14"][-1]


# ---------------------------------------------------------------------------
# Window truncation
# ---------------------------------------------------------------------------


def test_window_overflow_truncates_to_window_size() -> None:
    engine = TechnicalFeatureEngine(window_size=50)
    df = feed(engine, 60)
    assert df.height == 50


def test_exactly_window_size_rows_not_truncated() -> None:
    engine = TechnicalFeatureEngine(window_size=30)
    df = feed(engine, 30)
    assert df.height == 30


# ---------------------------------------------------------------------------
# Symbol isolation
# ---------------------------------------------------------------------------


def test_two_symbols_independent() -> None:
    engine = TechnicalFeatureEngine()
    for i in range(10):
        engine.update(make_candle(close=100.0 + i, offset_minutes=i, symbol="INFY"))
        engine.update(make_candle(close=200.0 + i, offset_minutes=i, symbol="TCS"))

    infy = engine.get("INFY", "1min")
    tcs = engine.get("TCS", "1min")
    assert infy is not None and tcs is not None
    assert infy.height == 10
    assert tcs.height == 10
    # Close prices are distinct
    assert infy["close"][-1] != tcs["close"][-1]


# ---------------------------------------------------------------------------
# Cold start / edge cases
# ---------------------------------------------------------------------------


def test_single_candle_no_exception() -> None:
    engine = TechnicalFeatureEngine()
    df = engine.update(make_candle(close=100.0))
    assert df.height == 1


def test_get_returns_none_for_unknown_symbol() -> None:
    engine = TechnicalFeatureEngine()
    assert engine.get("UNKNOWN", "1min") is None


def test_update_returns_new_dataframe_not_mutating() -> None:
    engine = TechnicalFeatureEngine()
    df1 = engine.update(make_candle(close=100.0, offset_minutes=0))
    df2 = engine.update(make_candle(close=101.0, offset_minutes=1))
    # df1 had height=1; engine returned a new df so df1 is unchanged
    assert df1.height == 1
    assert df2.height == 2


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------


def test_vwap_equals_close_for_single_candle() -> None:
    engine = TechnicalFeatureEngine()
    df = engine.update(make_candle(close=100.0, volume=500))
    # Single candle: vwap = close * volume / volume = close
    assert df["vwap"][0] == pytest.approx(100.0)


def test_vwap_weighted_average_two_candles() -> None:
    engine = TechnicalFeatureEngine()
    engine.update(make_candle(close=100.0, volume=100, offset_minutes=0))
    df = engine.update(make_candle(close=200.0, volume=100, offset_minutes=1))
    # vwap = (100*100 + 200*100) / 200 = 150
    assert df["vwap"][-1] == pytest.approx(150.0)


def test_vwap_resets_at_new_session_boundary() -> None:
    """VWAP must restart its cumulative average at 09:15 IST (UTC 03:45) each day."""
    engine = TechnicalFeatureEngine()

    # Day 1: session opens at BASE_TIME (09:15 IST). Feed two candles.
    # VWAP after day 1 should be (100*200 + 200*200) / 400 = 150.
    engine.update(make_candle(close=100.0, volume=200, offset_minutes=0))  # 09:15 IST day 1
    engine.update(make_candle(close=200.0, volume=200, offset_minutes=1))  # 09:16 IST day 1

    # Day 2: session opens exactly 24h later (same UTC offset_minutes=1440).
    # After the reset candle (100 @ day 2 open), VWAP should be 100 — NOT a
    # continuation of day 1's 150 average.
    engine.update(make_candle(close=100.0, volume=200, offset_minutes=1440))  # 09:15 IST day 2
    df = engine.get("INFY", "1min")
    assert df is not None

    # The last row's VWAP must equal its own close (first bar of new session)
    vwap_last = df["vwap"][-1]
    assert vwap_last == pytest.approx(
        100.0
    ), f"VWAP should reset to the first bar's price at session open, got {vwap_last}"


def test_vwap_accumulates_within_session() -> None:
    """VWAP keeps accumulating across bars within the same session."""
    engine = TechnicalFeatureEngine()

    # All within day 1 session (minutes 0, 1, 2 from BASE_TIME = 09:15, 09:16, 09:17 IST)
    engine.update(make_candle(close=100.0, volume=100, offset_minutes=0))
    engine.update(make_candle(close=200.0, volume=100, offset_minutes=1))
    df = engine.update(make_candle(close=150.0, volume=200, offset_minutes=2))

    # vwap = (100*100 + 200*100 + 150*200) / (100+100+200) = 60000/400 = 150
    assert df["vwap"][-1] == pytest.approx(150.0)


def test_vwap_zero_volume_no_error() -> None:
    engine = TechnicalFeatureEngine()
    # Zero volume should produce NaN (not ZeroDivisionError)
    df = engine.update(make_candle(close=100.0, volume=0))
    # vwap should be NaN or null when volume=0
    vwap = df["vwap"][0]
    assert vwap is None or (isinstance(vwap, float) and math.isnan(vwap))
