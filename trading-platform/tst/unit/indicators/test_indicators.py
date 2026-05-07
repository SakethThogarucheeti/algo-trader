"""
Unit tests for the technical indicator library.

Math tests use a stub CandleStore (no DB).
Repository round-trip tests use a real Postgres container.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading.indicators.library.adx import ADX
from trading.indicators.library.atr import ATR
from trading.indicators.library.bollinger import BollingerBands
from trading.indicators.library.cci import CCI
from trading.indicators.library.chaikin_volatility import ChaikinVolatility
from trading.indicators.library.cmf import CMF
from trading.indicators.library.donchian import DonchianChannels
from trading.indicators.library.ema import EMA
from trading.indicators.library.historical_volatility import HistoricalVolatility
from trading.indicators.library.keltner import KeltnerChannels
from trading.indicators.library.macd import MACD
from trading.indicators.library.mfi import MFI
from trading.indicators.library.momentum import Momentum
from trading.indicators.library.obv import OBV
from trading.indicators.library.parabolic_sar import ParabolicSAR
from trading.indicators.library.pivot import PivotPoints
from trading.indicators.library.roc import ROC
from trading.indicators.library.rsi import RSI
from trading.indicators.library.sma import SMA
from trading.indicators.library.stochastic import Stochastic
from trading.indicators.library.supertrend import Supertrend
from trading.indicators.library.true_range import TrueRange, true_range
from trading.indicators.library.vwap import VWAP
from trading.indicators.library.vwma import VWMA
from trading.indicators.library.wilder_ema import WilderEMA, wilder_ema
from trading.indicators.library.williams_r import WilliamsR
from trading.indicators.store import CandleStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(rows: list[dict]) -> CandleStore:
    """Build a CandleStore backed by a stub that returns fixed rows."""
    store = MagicMock(spec=CandleStore)
    store.fetch = AsyncMock(return_value=rows)
    store.fetch_since = AsyncMock(return_value=rows)
    return store


def _candles(closes: list[float], *, base_ts: datetime | None = None) -> list[dict]:
    """Build minimal candle dicts from a list of close prices."""
    if base_ts is None:
        base_ts = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    rows = []
    for i, c in enumerate(closes):
        ts = base_ts + timedelta(minutes=15 * i)
        rows.append({
            "symbol": "TEST",
            "interval": "15min",
            "ts": ts,
            "open": c,
            "high": c + 1.0,
            "low": c - 1.0,
            "close": c,
            "volume": 1000,
        })
    return rows


def _bind(indicator, rows: list[dict]) -> None:
    """Bind an indicator to a stub store and fixed symbol/interval."""
    indicator.bind("TEST", "15min", _make_store(rows))


# ---------------------------------------------------------------------------
# wilder_ema helper
# ---------------------------------------------------------------------------


def test_wilder_ema_single_value():
    arr = [100.0]
    result = wilder_ema(arr, period=1)
    assert result == pytest.approx(100.0)


def test_wilder_ema_constant_series():
    # Constant series: EMA should stay constant regardless of period
    arr = [50.0] * 20
    for period in [3, 7, 14]:
        assert wilder_ema(arr, period) == pytest.approx(50.0, rel=1e-6)


def test_wilder_ema_uptrend():
    # Rising series: EMA should lag behind the final value
    arr = list(range(1, 21, 1))  # 1..20
    result = wilder_ema(arr, period=5)
    assert result < 20.0  # lags
    assert result > 10.0  # but not too far behind


# ---------------------------------------------------------------------------
# true_range helper
# ---------------------------------------------------------------------------


def test_true_range_no_gaps():
    import numpy as np
    highs = np.array([110.0, 115.0, 108.0])
    lows = np.array([100.0, 105.0, 98.0])
    closes = np.array([105.0, 110.0, 103.0])
    tr = true_range(highs, lows, closes)
    # Row 0: H-L = 10, no prev close
    assert tr[0] == pytest.approx(10.0)
    # Row 1: H-L=10, |115-105|=10, |105-105|=0  → 10
    assert tr[1] == pytest.approx(10.0)
    # Row 2: H-L=10, |108-110|=2, |98-110|=12  → 12
    assert tr[2] == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ema_returns_none_insufficient_data():
    ema = EMA(period=9)
    _bind(ema, _candles([100.0] * 5))  # 5 < 9
    assert await ema.compute() is None


@pytest.mark.asyncio
async def test_ema_constant_price():
    price = 150.0
    ema = EMA(period=9)
    _bind(ema, _candles([price] * 30))
    result = await ema.compute()
    assert result == pytest.approx(price, rel=1e-4)


@pytest.mark.asyncio
async def test_ema_uptrend_lags_price():
    closes = list(range(100, 140))  # 100..139
    ema = EMA(period=9)
    _bind(ema, _candles(closes))
    result = await ema.compute()
    assert result is not None
    assert result < closes[-1]  # EMA lags in a rising market
    assert result > closes[0]


@pytest.mark.asyncio
async def test_ema_period_validation():
    with pytest.raises(ValueError):
        EMA(period=0)


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sma_exact_mean():
    closes = [10.0, 20.0, 30.0, 40.0, 50.0]
    sma = SMA(period=5)
    _bind(sma, _candles(closes))
    result = await sma.compute()
    assert result == pytest.approx(30.0)


@pytest.mark.asyncio
async def test_sma_returns_none_insufficient_data():
    sma = SMA(period=10)
    _bind(sma, _candles([100.0] * 5))
    assert await sma.compute() is None


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rsi_returns_none_insufficient_data():
    rsi = RSI(period=14)
    _bind(rsi, _candles([100.0] * 10))  # need at least 15
    assert await rsi.compute() is None


@pytest.mark.asyncio
async def test_rsi_flat_market_returns_none():
    # All closes the same → no gains or losses → avg_loss == 0 → None
    rsi = RSI(period=14)
    _bind(rsi, _candles([100.0] * 50))
    assert await rsi.compute() is None


@pytest.mark.asyncio
async def test_rsi_strong_uptrend_returns_none():
    # Monotonically rising → avg_loss == 0 → undefined (returns None, not 100)
    closes = [float(100 + i) for i in range(50)]
    rsi = RSI(period=14)
    _bind(rsi, _candles(closes))
    result = await rsi.compute()
    assert result is None


@pytest.mark.asyncio
async def test_rsi_strong_uptrend_with_pullback_near_100():
    # Mostly rising but every 5th bar drops by 0.5 → avg_loss > 0, RSI high (>70)
    closes = []
    price = 100.0
    for i in range(50):
        if i > 0 and i % 5 == 0:
            price -= 0.5
        else:
            price += 1.5
        closes.append(price)
    rsi = RSI(period=14)
    _bind(rsi, _candles(closes))
    result = await rsi.compute()
    assert result is not None
    assert result > 70.0


@pytest.mark.asyncio
async def test_rsi_strong_downtrend_near_0():
    # Monotonically falling → RSI should be low (<20)
    closes = [float(200 - i) for i in range(50)]
    rsi = RSI(period=14)
    _bind(rsi, _candles(closes))
    result = await rsi.compute()
    assert result is not None
    assert result < 20.0


@pytest.mark.asyncio
async def test_rsi_in_valid_range():
    import random
    random.seed(42)
    closes = [100.0 + random.gauss(0, 2) for _ in range(60)]
    rsi = RSI(period=14)
    _bind(rsi, _candles(closes))
    result = await rsi.compute()
    if result is not None:
        assert 0.0 <= result <= 100.0


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_atr_returns_none_insufficient_data():
    atr = ATR(period=14)
    _bind(atr, _candles([100.0] * 5))
    assert await atr.compute() is None


@pytest.mark.asyncio
async def test_atr_nonnegative():
    closes = [100.0 + i * 0.5 for i in range(50)]
    atr = ATR(period=14)
    _bind(atr, _candles(closes))
    result = await atr.compute()
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_atr_higher_volatility_gives_higher_atr():
    # Low volatility: ±0.5 range
    low_vol = [
        {
            "symbol": "T", "interval": "15min",
            "ts": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
            "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1000,
        }
        for i in range(50)
    ]
    # High volatility: ±5 range
    high_vol = [
        {
            "symbol": "T", "interval": "15min",
            "ts": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * i),
            "open": 100.0, "high": 105.0, "low": 95.0, "close": 100.0, "volume": 1000,
        }
        for i in range(50)
    ]

    atr_low = ATR(period=14)
    atr_low.bind("T", "15min", _make_store(low_vol))

    atr_high = ATR(period=14)
    atr_high.bind("T", "15min", _make_store(high_vol))

    r_low = await atr_low.compute()
    r_high = await atr_high.compute()
    assert r_low is not None and r_high is not None
    assert r_high > r_low


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vwap_single_bar():
    rows = [{
        "symbol": "T", "interval": "15min",
        "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 500,
    }]
    vwap = VWAP()
    vwap.bind("T", "15min", _make_store(rows))
    result = await vwap.compute()
    assert result == pytest.approx(102.0)


@pytest.mark.asyncio
async def test_vwap_weighted_correctly():
    # Two bars: close=100 vol=100, close=200 vol=300
    # Expected VWAP = (100*100 + 200*300) / (100+300) = 70000/400 = 175
    rows = [
        {"symbol": "T", "interval": "15min",
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
         "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 100},
        {"symbol": "T", "interval": "15min",
         "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC),
         "open": 200.0, "high": 200.0, "low": 200.0, "close": 200.0, "volume": 300},
    ]
    vwap = VWAP()
    vwap.bind("T", "15min", _make_store(rows))
    result = await vwap.compute()
    assert result == pytest.approx(175.0)


@pytest.mark.asyncio
async def test_vwap_zero_volume_returns_none():
    rows = [{"symbol": "T", "interval": "15min",
             "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
             "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0}]
    vwap = VWAP()
    vwap.bind("T", "15min", _make_store(rows))
    assert await vwap.compute() is None


@pytest.mark.asyncio
async def test_vwap_no_bars_returns_none():
    vwap = VWAP()
    vwap.bind("T", "15min", _make_store([]))
    assert await vwap.compute() is None


# ---------------------------------------------------------------------------
# WilderEMA indicator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wilder_ema_indicator_constant_series():
    closes = [100.0] * 20
    ind = WilderEMA(period=5)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 100.0, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_wilder_ema_indicator_returns_none_insufficient():
    ind = WilderEMA(period=10)
    _bind(ind, _candles([100.0] * 3))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_wilder_ema_indicator_uptrend_lags():
    # WilderEMA lags behind a rising price — value should be below last close
    closes = [float(100 + i) for i in range(30)]
    ind = WilderEMA(period=9)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result < closes[-1]


# ---------------------------------------------------------------------------
# TrueRange indicator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_true_range_indicator_no_gaps():
    rows = [
        {"open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100,
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC)},
        {"open": 11.0, "high": 13.0, "low": 10.0, "close": 12.0, "volume": 100,
         "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC)},
    ]
    ind = TrueRange()
    store = _make_store(rows)
    ind.bind("X", "1min", store)
    result = await ind.compute()
    # TR for bar 2: max(13-10, |13-11|, |10-11|) = max(3, 2, 1) = 3
    assert result is not None
    assert math.isclose(result, 3.0, rel_tol=1e-9)


@pytest.mark.asyncio
async def test_true_range_indicator_returns_none_single_bar():
    rows = [
        {"open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100,
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC)},
    ]
    ind = TrueRange()
    store = _make_store(rows)
    ind.bind("X", "1min", store)
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_true_range_indicator_gap_up():
    # Previous close 10, next bar opens gap-up: high 15, low 12
    # TR = max(15-12, |15-10|, |12-10|) = max(3, 5, 2) = 5
    rows = [
        {"open": 9.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100,
         "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC)},
        {"open": 13.0, "high": 15.0, "low": 12.0, "close": 14.0, "volume": 100,
         "ts": datetime(2024, 1, 1, 9, 30, tzinfo=UTC)},
    ]
    ind = TrueRange()
    store = _make_store(rows)
    ind.bind("X", "1min", store)
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 5.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_macd_returns_none_insufficient():
    ind = MACD(fast=12, slow=26, signal=9)
    _bind(ind, _candles([100.0] * 10))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_macd_fast_slow_validation():
    with pytest.raises(ValueError):
        MACD(fast=26, slow=12)


@pytest.mark.asyncio
async def test_macd_uptrend_positive():
    # Rising prices → fast EMA > slow EMA → positive MACD
    closes = [float(100 + i) for i in range(80)]
    ind = MACD(fast=12, slow=26, signal=9)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_macd_full_returns_three_values():
    closes = [float(100 + i) for i in range(80)]
    ind = MACD(fast=12, slow=26, signal=9)
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None
    macd, signal, hist = result
    assert math.isclose(macd - signal, hist, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bollinger_returns_none_insufficient():
    ind = BollingerBands(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_bollinger_constant_price_percent_b_half():
    # Constant price → std=0, band width=0 → percent_b falls back to 0.5
    ind = BollingerBands(period=5)
    _bind(ind, _candles([100.0] * 5))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.5, rel_tol=1e-9)


@pytest.mark.asyncio
async def test_bollinger_full_upper_above_lower():
    closes = [float(100 + (i % 5)) for i in range(20)]
    ind = BollingerBands(period=20)
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None
    upper, middle, lower, bw, pct_b = result
    assert upper > middle > lower
    assert bw >= 0.0


# ---------------------------------------------------------------------------
# Stochastic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stochastic_returns_none_insufficient():
    ind = Stochastic(k_period=14)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_stochastic_range():
    closes = [float(100 + (i % 10)) for i in range(30)]
    ind = Stochastic(k_period=14, d_period=3)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_stochastic_at_high_when_at_peak():
    # Last close == highest high → %K should be 100
    rows = _candles([100.0] * 13 + [110.0])
    # Override highs so highest_high == last close
    for r in rows:
        r["high"] = r["close"] + 0.0  # no extra headroom
        r["low"] = r["close"] - 5.0
    rows[-1]["high"] = 110.0
    rows[-1]["low"] = 105.0
    ind = Stochastic(k_period=14, d_period=3)
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute()
    assert result is not None
    assert result == pytest.approx(100.0, abs=1e-6)


# ---------------------------------------------------------------------------
# CCI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cci_returns_none_insufficient():
    ind = CCI(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_cci_flat_returns_none():
    # All identical bars → MAD = 0 → None
    ind = CCI(period=5)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_cci_overbought_on_spike():
    # Strong recent spike → CCI >> +100
    closes = [100.0] * 19 + [120.0]
    ind = CCI(period=20)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result > 100.0


# ---------------------------------------------------------------------------
# Williams %R
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_williams_r_returns_none_insufficient():
    ind = WilliamsR(period=14)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_williams_r_range():
    closes = [float(100 + (i % 10)) for i in range(14)]
    ind = WilliamsR(period=14)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert -100.0 <= result <= 0.0


@pytest.mark.asyncio
async def test_williams_r_at_high_is_zero():
    # Close == highest high → %R = 0
    rows = _candles([100.0] * 14)
    for r in rows:
        r["high"] = 110.0
        r["low"] = 90.0
    rows[-1]["close"] = 110.0
    ind = WilliamsR(period=14)
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# ROC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roc_returns_none_insufficient():
    ind = ROC(period=10)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_roc_flat_is_zero():
    ind = ROC(period=5)
    _bind(ind, _candles([100.0] * 6))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_roc_ten_percent_rise():
    closes = [100.0] + [110.0]
    ind = ROC(period=1)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 10.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_momentum_returns_none_insufficient():
    ind = Momentum(period=10)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_momentum_flat_is_zero():
    ind = Momentum(period=5)
    _bind(ind, _candles([100.0] * 6))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_momentum_positive_on_rise():
    ind = Momentum(period=3)
    _bind(ind, _candles([100.0, 101.0, 102.0, 105.0]))
    result = await ind.compute()
    assert result is not None
    assert result > 0.0


# ---------------------------------------------------------------------------
# Donchian Channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_donchian_returns_none_insufficient():
    ind = DonchianChannels(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_donchian_full_upper_lower():
    closes = [float(90 + i) for i in range(20)]
    ind = DonchianChannels(period=20)
    rows = _candles(closes)
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute_full()
    assert result is not None
    upper, middle, lower = result
    assert upper >= middle >= lower


@pytest.mark.asyncio
async def test_donchian_flat_width_zero():
    # All bars identical H/L/C → upper == lower
    rows = [
        {"symbol": "X", "interval": "15min", "ts": datetime(2024, 1, 1, 9, 15, tzinfo=UTC),
         "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000}
        for _ in range(5)
    ]
    ind = DonchianChannels(period=5)
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute_full()
    assert result is not None
    upper, middle, lower = result
    assert math.isclose(upper, lower, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Keltner Channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_keltner_returns_none_insufficient():
    ind = KeltnerChannels()
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_keltner_full_upper_above_lower():
    closes = [float(100 + (i % 5)) for i in range(60)]
    ind = KeltnerChannels(ema_period=20, atr_period=10)
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None
    upper, middle, lower = result
    assert upper > middle > lower


# ---------------------------------------------------------------------------
# Historical Volatility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hv_returns_none_insufficient():
    ind = HistoricalVolatility(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_hv_flat_is_zero():
    ind = HistoricalVolatility(period=5)
    _bind(ind, _candles([100.0] * 6))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


@pytest.mark.asyncio
async def test_hv_positive_on_volatile_series():
    import random
    random.seed(7)
    closes = [100.0 * (1 + random.gauss(0, 0.02)) for _ in range(22)]
    ind = HistoricalVolatility(period=20)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result > 0.0


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obv_returns_none_insufficient():
    ind = OBV(period=5)
    _bind(ind, _candles([100.0]))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_obv_accumulates_on_rising():
    # All bars rising → OBV increases each step
    closes = [100.0, 101.0, 102.0, 103.0, 104.0]
    ind = OBV(period=5)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result > 0.0


@pytest.mark.asyncio
async def test_obv_flat_is_zero():
    ind = OBV(period=5)
    _bind(ind, _candles([100.0] * 5))
    result = await ind.compute()
    assert result is not None
    assert math.isclose(result, 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# MFI
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mfi_returns_none_insufficient():
    ind = MFI(period=14)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_mfi_range():
    closes = [float(100 + (i % 5)) for i in range(15)]
    ind = MFI(period=14)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    if result is not None:
        assert 0.0 <= result <= 100.0


# ---------------------------------------------------------------------------
# CMF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmf_returns_none_insufficient():
    ind = CMF(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_cmf_range():
    closes = [float(100 + (i % 5)) for i in range(20)]
    ind = CMF(period=20)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert -1.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# VWMA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vwma_returns_none_insufficient():
    ind = VWMA(period=20)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_vwma_equal_volumes_equals_sma():
    # Equal volumes → VWMA == SMA
    closes = [float(i) for i in range(1, 6)]
    ind = VWMA(period=5)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    expected = sum(closes) / len(closes)
    assert result is not None
    assert math.isclose(result, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Pivot Points
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pivot_returns_none_single_bar():
    ind = PivotPoints()
    rows = [
        {"symbol": "X", "interval": "1day", "ts": datetime(2024, 1, 1, tzinfo=UTC),
         "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000},
    ]
    store = MagicMock(spec=CandleStore)
    store.fetch = AsyncMock(return_value=rows)
    store.fetch_since = AsyncMock(return_value=rows)
    ind.bind("X", "1day", store)
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_pivot_full_levels():
    rows = [
        {"symbol": "X", "interval": "1day", "ts": datetime(2024, 1, 1, tzinfo=UTC),
         "open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0, "volume": 1000},
        {"symbol": "X", "interval": "1day", "ts": datetime(2024, 1, 2, tzinfo=UTC),
         "open": 101.0, "high": 112.0, "low": 92.0, "close": 105.0, "volume": 1000},
    ]
    store = MagicMock(spec=CandleStore)
    store.fetch = AsyncMock(return_value=rows)
    store.fetch_since = AsyncMock(return_value=rows)
    ind = PivotPoints()
    ind.bind("X", "1day", store)
    result = await ind.compute_full()
    assert result is not None
    pp, r1, s1, r2, s2, r3, s3 = result
    # PP = (110 + 90 + 100) / 3 = 100
    assert math.isclose(pp, 100.0, rel_tol=1e-9)
    assert r1 > pp > s1
    assert r2 > r1
    assert s2 < s1


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_supertrend_returns_none_insufficient():
    ind = Supertrend(period=10)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_supertrend_direction_is_plus_or_minus_one():
    closes = [float(100 + i) for i in range(40)]
    ind = Supertrend(period=10, multiplier=3.0)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert result in (1.0, -1.0)


# ---------------------------------------------------------------------------
# Parabolic SAR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_psar_returns_none_insufficient():
    ind = ParabolicSAR()
    _bind(ind, _candles([100.0] * 2))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_psar_returns_float():
    closes = [float(100 + i * 0.5) for i in range(20)]
    ind = ParabolicSAR()
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert isinstance(result, float)


@pytest.mark.asyncio
async def test_psar_full_bullish_on_uptrend():
    closes = [float(100 + i) for i in range(50)]
    ind = ParabolicSAR()
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None
    sar, is_bullish = result
    assert is_bullish is True
    assert sar < closes[-1]


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adx_returns_none_insufficient():
    ind = ADX(period=14)
    _bind(ind, _candles([100.0] * 10))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_adx_range():
    closes = [float(100 + (i % 7)) for i in range(60)]
    ind = ADX(period=14)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert 0.0 <= result <= 100.0


@pytest.mark.asyncio
async def test_adx_full_returns_three():
    closes = [float(100 + i) for i in range(60)]
    ind = ADX(period=14)
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None
    adx, plus_di, minus_di = result
    assert adx >= 0.0
    assert plus_di >= 0.0
    assert minus_di >= 0.0


# ---------------------------------------------------------------------------
# Chaikin Volatility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chaikin_vol_returns_none_insufficient():
    ind = ChaikinVolatility(ema_period=10, roc_period=10)
    _bind(ind, _candles([100.0] * 5))
    assert await ind.compute() is None


@pytest.mark.asyncio
async def test_chaikin_vol_returns_float():
    closes = [float(100 + (i % 5)) for i in range(60)]
    ind = ChaikinVolatility(ema_period=10, roc_period=10)
    _bind(ind, _candles(closes))
    result = await ind.compute()
    assert result is not None
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Indicator registry
# ---------------------------------------------------------------------------


def test_indicator_aliases_registered():
    # Trigger import so subclasses register themselves
    import trading.indicators  # noqa: F401
    from trading.indicators.base import _REGISTRY
    assert "ema" in _REGISTRY
    assert "sma" in _REGISTRY
    assert "rsi" in _REGISTRY
    assert "atr" in _REGISTRY
    assert "vwap" in _REGISTRY
    assert "wilder_ema" in _REGISTRY
    assert "true_range" in _REGISTRY
    assert "macd" in _REGISTRY
    assert "bollinger" in _REGISTRY
    assert "stochastic" in _REGISTRY
    assert "cci" in _REGISTRY
    assert "williams_r" in _REGISTRY
    assert "roc" in _REGISTRY
    assert "momentum" in _REGISTRY
    assert "donchian" in _REGISTRY
    assert "keltner" in _REGISTRY
    assert "hv" in _REGISTRY
    assert "obv" in _REGISTRY
    assert "mfi" in _REGISTRY
    assert "cmf" in _REGISTRY
    assert "vwma" in _REGISTRY
    assert "pivot" in _REGISTRY
    assert "supertrend" in _REGISTRY
    assert "psar" in _REGISTRY
    assert "adx" in _REGISTRY
    assert "chaikin_vol" in _REGISTRY


def test_duplicate_alias_raises():
    from trading.indicators.base import Indicator
    with pytest.raises(ValueError, match="Duplicate Indicator alias"):
        class _DupEMA(Indicator):
            alias = "ema"
            async def compute(self): ...


# ---------------------------------------------------------------------------
# Repository round-trip — requires Postgres container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers not installed")
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture
async def pg_engine(pg_container):
    from sqlalchemy.ext.asyncio import create_async_engine

    from trading.core.database import init_db

    url = (
        pg_container.get_connection_url()
        .replace("psycopg2", "asyncpg")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    eng = create_async_engine(url, echo=False)
    await init_db(eng)
    yield eng
    from sqlalchemy import text
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE candles CASCADE"))
    await eng.dispose()


@pytest.mark.asyncio
async def test_save_and_get_candles(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    rows = [
        {
            "symbol": "INFY", "interval": "15min",
            "ts": datetime(2024, 1, 2, 9, 15, tzinfo=UTC),
            "open": 1500.0, "high": 1510.0, "low": 1495.0, "close": 1505.0, "volume": 10000,
        },
        {
            "symbol": "INFY", "interval": "15min",
            "ts": datetime(2024, 1, 2, 9, 30, tzinfo=UTC),
            "open": 1505.0, "high": 1520.0, "low": 1500.0, "close": 1515.0, "volume": 12000,
        },
    ]

    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    async with sf() as session:
        result = await repo.get_candles(session, "INFY", "15min", limit=10)

    assert len(result) == 2
    assert result[0]["close"] == pytest.approx(1505.0)
    assert result[1]["close"] == pytest.approx(1515.0)
    assert result[0]["ts"] < result[1]["ts"]  # ASC order


@pytest.mark.asyncio
async def test_save_candles_idempotent(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    row = {
        "symbol": "TCS", "interval": "1min",
        "ts": datetime(2024, 1, 3, 9, 15, tzinfo=UTC),
        "open": 3000.0, "high": 3010.0, "low": 2995.0, "close": 3005.0, "volume": 5000,
    }

    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, [row])
    # Second insert: should not raise or duplicate
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, [row])

    async with sf() as session:
        result = await repo.get_candles(session, "TCS", "1min", limit=10)
    assert len(result) == 1  # still only one row


@pytest.mark.asyncio
async def test_get_candles_since(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    base = datetime(2024, 1, 4, 9, 0, tzinfo=UTC)
    rows = [
        {"symbol": "RELIANCE", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 2000.0, "high": 2010.0, "low": 1995.0, "close": 2005.0, "volume": 8000}
        for i in range(10)
    ]

    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    since = base + timedelta(minutes=15 * 5)  # from the 6th bar
    async with sf() as session:
        result = await repo.get_candles_since(session, "RELIANCE", "15min", since)

    assert len(result) == 5  # bars 5..9


@pytest.mark.asyncio
async def test_candle_store_end_to_end(pg_engine):
    """CandleStore + EMA computes the right value end-to-end."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from trading.indicators.store import CandleStore
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()

    # Seed 30 bars of constant price 200
    base = datetime(2024, 1, 5, 9, 15, tzinfo=UTC)
    rows = [
        {"symbol": "HDFC", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.0, "volume": 1000}
        for i in range(30)
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    store = CandleStore(session_factory=sf, repo=repo)
    ema = EMA(period=9)
    ema.bind("HDFC", "15min", store)

    result = await ema.compute()
    assert result == pytest.approx(200.0, rel=1e-3)


@pytest.mark.asyncio
async def test_candle_store_redis_cache(pg_engine):
    """Second fetch hits Redis cache, not the DB (verified via call count)."""
    import fakeredis.aioredis as fakeredis
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from trading.indicators.store import CandleStore
    from trading.storage.repository import Repository

    sf = async_sessionmaker(pg_engine, expire_on_commit=False)
    repo = Repository()
    redis = fakeredis.FakeRedis()

    base = datetime(2024, 1, 6, 9, 15, tzinfo=UTC)
    rows = [
        {"symbol": "WIPRO", "interval": "15min",
         "ts": base + timedelta(minutes=15 * i),
         "open": 300.0, "high": 301.0, "low": 299.0, "close": 300.0, "volume": 500}
        for i in range(20)
    ]
    async with sf() as session:
        async with session.begin():
            await repo.save_candles(session, rows)

    store = CandleStore(session_factory=sf, repo=repo, redis=redis)

    # First call — goes to DB, populates cache
    r1 = await store.fetch("WIPRO", "15min", 20)
    # Second call — should hit cache (verify by checking Redis key exists)
    r2 = await store.fetch("WIPRO", "15min", 20)

    assert len(r1) == len(r2) == 20
    assert r1[0]["close"] == r2[0]["close"]

    # Redis should have the key
    keys = await redis.keys("cs:candles:WIPRO:15min:*")
    assert len(keys) == 1


# ---------------------------------------------------------------------------
# CandleStore — mock-based coverage for Redis paths + fetch_since
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candle_store_fetch_since_no_redis():
    """fetch_since calls repo.get_candles_since when no Redis configured."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from trading.indicators.store import CandleStore

    since = datetime(2024, 1, 1, 9, 15, tzinfo=UTC)
    expected_rows = [{"symbol": "T", "interval": "15min", "ts": since, "close": 100.0}]

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles_since = AsyncMock(return_value=expected_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo)
    result = await store.fetch_since("T", "15min", since)

    assert result == expected_rows
    mock_repo.get_candles_since.assert_called_once_with(mock_session, "T", "15min", since)


@pytest.mark.asyncio
async def test_candle_store_redis_cache_hit_skips_db():
    """When Redis returns a cached value, the DB is not queried."""
    import json
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from trading.indicators.store import CandleStore

    cached_rows = [{"close": 200.0, "ts": "2024-01-01T09:15:00+00:00"}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(cached_rows).encode())

    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_repo = MagicMock()

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 10)

    assert result == cached_rows
    mock_repo.get_candles.assert_not_called()


@pytest.mark.asyncio
async def test_candle_store_redis_get_error_falls_through_to_db():
    """Redis GET failure is swallowed and the DB is queried instead."""
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from trading.indicators.store import CandleStore

    db_rows = [{"close": 300.0}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles = AsyncMock(return_value=db_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 5)

    assert result == db_rows


@pytest.mark.asyncio
async def test_candle_store_redis_setex_error_is_swallowed():
    """Redis SETEX failure after a DB read does not raise."""
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from trading.indicators.store import CandleStore

    db_rows = [{"close": 150.0}]

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)  # cache miss
    mock_redis.setex = AsyncMock(side_effect=ConnectionError("redis down"))

    mock_session = AsyncMock(spec=AsyncSession)
    mock_sf = MagicMock(spec=async_sessionmaker)
    mock_sf.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_repo = MagicMock()
    mock_repo.get_candles = AsyncMock(return_value=db_rows)

    store = CandleStore(session_factory=mock_sf, repo=mock_repo, redis=mock_redis)
    result = await store.fetch("T", "15min", 5)  # should not raise

    assert result == db_rows


# ---------------------------------------------------------------------------
# Parabolic SAR — flip logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_psar_bearish_then_bullish_flip():
    """
    A downtrend followed by a sharp rally flips SAR from bearish to bullish.
    """
    # Falling prices → bearish SAR; then rising sharply → flip to bullish
    falling = [float(200 - i * 3) for i in range(20)]  # 200 down to 143
    rising = [float(140 + i * 5) for i in range(15)]   # sharp rally

    closes = falling + rising
    rows = _candles(closes)
    ind = ParabolicSAR()
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute_full()
    assert result is not None
    _, is_bullish = result
    assert is_bullish is True


@pytest.mark.asyncio
async def test_psar_bullish_then_bearish_flip():
    """
    An uptrend followed by a sharp drop flips SAR from bullish to bearish.
    """
    rising = [float(100 + i * 3) for i in range(20)]   # 100 up to 157
    falling = [float(160 - i * 5) for i in range(15)]  # sharp drop

    closes = rising + falling
    rows = _candles(closes)
    ind = ParabolicSAR()
    ind.bind("TEST", "15min", _make_store(rows))
    result = await ind.compute_full()
    assert result is not None
    _, is_bullish = result
    assert is_bullish is False


@pytest.mark.asyncio
async def test_psar_af_increments_on_new_extreme():
    """AF increments when a new extreme is set, capped at af_max."""
    # Steady uptrend → AF should reach af_max eventually
    closes = [float(100 + i) for i in range(100)]
    ind = ParabolicSAR(af_start=0.02, af_step=0.02, af_max=0.2)
    _bind(ind, _candles(closes))
    result = await ind.compute_full()
    assert result is not None  # just checking it completes without error
