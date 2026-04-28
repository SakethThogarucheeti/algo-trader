"""Tests for all strategy implementations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from trading.core.schemas import InstrumentType, Side
from trading.strategy.base import Strategy
from trading.strategy.ema_crossover import EmaCrossoverStrategy
from trading.strategy.opening_range_breakout import OpeningRangeBreakoutStrategy
from trading.strategy.rsi_mean_reversion import RsiMeanReversionStrategy
from trading.strategy.vwap_reversion import VwapReversionStrategy

EQUITY = InstrumentType.EQUITY
# 09:45 UTC = 15:15 IST (well past ORB window)
BASE_TS = datetime(2025, 1, 6, 4, 15, tzinfo=UTC)  # 09:45 IST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _df_with_rsi(rsi_values: list[float], atr: float = 10.0) -> pl.DataFrame:
    n = len(rsi_values)
    return pl.DataFrame({
        "close": [100.0 + i for i in range(n)],
        "rsi_14": rsi_values,
        "atr_14": [atr] * n,
    })


def _df_with_vwap(
    closes: list[float],
    vwaps: list[float],
    atr: float = 10.0,
) -> pl.DataFrame:
    n = len(closes)
    return pl.DataFrame({
        "close": closes,
        "vwap": vwaps,
        "atr_14": [atr] * n,
    })


def _orb_df(
    n_bars: int,
    highs: list[float],
    lows: list[float],
    closes: list[float],
    atrs: list[float],
    *,
    base_ts: datetime,
    interval_mins: int = 15,
) -> pl.DataFrame:
    timestamps = [base_ts + timedelta(minutes=i * interval_mins) for i in range(n_bars)]
    return pl.DataFrame({
        "timestamp": timestamps,
        "high": highs,
        "low": lows,
        "close": closes,
        "atr_14": atrs,
    })


# ---------------------------------------------------------------------------
# RsiMeanReversionStrategy
# ---------------------------------------------------------------------------


def test_rsi_buy_signal_on_oversold_cross() -> None:
    strat = RsiMeanReversionStrategy()
    df = _df_with_rsi([25.0, 32.0])  # prev below 30, cur above 30 → BUY
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_rsi_sell_signal_on_overbought_cross() -> None:
    strat = RsiMeanReversionStrategy()
    df = _df_with_rsi([75.0, 68.0])  # prev above 70, cur below 70 → SELL
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_rsi_no_signal_when_rsi_within_range() -> None:
    strat = RsiMeanReversionStrategy()
    df = _df_with_rsi([50.0, 55.0])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_rsi_no_signal_when_only_one_row() -> None:
    strat = RsiMeanReversionStrategy()
    df = _df_with_rsi([25.0])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_rsi_no_signal_when_missing_column() -> None:
    strat = RsiMeanReversionStrategy()
    df = pl.DataFrame({"close": [100.0, 101.0]})
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_rsi_no_signal_when_atr_zero() -> None:
    strat = RsiMeanReversionStrategy()
    df = _df_with_rsi([25.0, 32.0], atr=0.0)
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_rsi_strategy_id() -> None:
    assert RsiMeanReversionStrategy().id == "rsi_mean_reversion"


def test_rsi_invalid_params_raise() -> None:
    with pytest.raises(ValueError):
        RsiMeanReversionStrategy(oversold=70.0, overbought=30.0)


def test_rsi_stop_distance_uses_atr_multiplier() -> None:
    strat = RsiMeanReversionStrategy(atr_multiplier=2.0)
    df = _df_with_rsi([25.0, 32.0], atr=10.0)
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.stop_distance == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# VwapReversionStrategy
# ---------------------------------------------------------------------------


def test_vwap_buy_signal_price_below_vwap_turning_up() -> None:
    strat = VwapReversionStrategy(vwap_band=1.0)
    # prev close was 10 below VWAP (≥ 1×ATR=10), cur close higher
    df = _df_with_vwap([90.0, 92.0], [100.0, 100.0], atr=10.0)
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_vwap_sell_signal_price_above_vwap_turning_down() -> None:
    strat = VwapReversionStrategy(vwap_band=1.0)
    # prev close was 10 above VWAP, cur close lower
    df = _df_with_vwap([110.0, 108.0], [100.0, 100.0], atr=10.0)
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_vwap_no_signal_deviation_below_band() -> None:
    strat = VwapReversionStrategy(vwap_band=2.0)
    # deviation=5, band=2×10=20 → not enough deviation
    df = _df_with_vwap([95.0, 92.0], [100.0, 100.0], atr=10.0)
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_vwap_no_signal_when_only_one_row() -> None:
    strat = VwapReversionStrategy()
    df = _df_with_vwap([90.0], [100.0])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_vwap_no_signal_when_missing_column() -> None:
    strat = VwapReversionStrategy()
    df = pl.DataFrame({"close": [90.0, 92.0]})
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_vwap_no_signal_when_atr_zero() -> None:
    strat = VwapReversionStrategy()
    df = _df_with_vwap([90.0, 92.0], [100.0, 100.0], atr=0.0)
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_vwap_strategy_id() -> None:
    assert VwapReversionStrategy().id == "vwap_reversion"


def test_vwap_invalid_band_raises() -> None:
    with pytest.raises(ValueError):
        VwapReversionStrategy(vwap_band=0.0)


# ---------------------------------------------------------------------------
# OpeningRangeBreakoutStrategy
# ---------------------------------------------------------------------------

# IST = UTC + 5:30.
# Session open = 09:15 IST = 03:45 UTC.
# ORB window with orb_bars=2, interval=15min → ends at 09:45 IST = 04:15 UTC.
# We use orb_bars=2 so tests need fewer bars.
_SESSION_OPEN_UTC = datetime(2025, 1, 6, 3, 45, tzinfo=UTC)   # 09:15 IST
_POST_ORB_UTC = datetime(2025, 1, 6, 4, 16, tzinfo=UTC)        # 09:46 IST — past 2-bar window


def _make_orb_bars(n: int, high: float = 105.0, low: float = 99.0) -> pl.DataFrame:
    """n bars starting at session open, establishing a known range."""
    rows = []
    for i in range(n):
        ts = _SESSION_OPEN_UTC + timedelta(minutes=i * 15)
        rows.append({
            "timestamp": ts, "high": high, "low": low,
            "close": (high + low) / 2, "atr_14": 5.0,
        })
    return pl.DataFrame(rows)


def _feed_orb_bars(strat: OpeningRangeBreakoutStrategy, range_df: pl.DataFrame) -> None:
    """Prime the strategy state by feeding each range bar as the last row of a growing df.

    Pads to meet the orb_bars+1 height guard by repeating the first row.
    """
    for i in range(1, range_df.height + 1):
        slice_df = range_df.slice(0, i)
        while slice_df.height < strat._orb_bars + 1:
            slice_df = pl.concat([slice_df.head(1), slice_df])
        strat.on_candle("INFY", EQUITY, slice_df)


def test_orb_buy_breakout_above_range() -> None:
    # orb_bars=2 → window = 09:15–09:45 IST (04:15 UTC).
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2)  # 09:15, 09:30 IST — both inside window

    # Feed range bars one-by-one to populate state
    _feed_orb_bars(strat, range_bars)

    # Breakout bar after ORB window: close above OR high (105)
    breakout_row = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [111.0], "low": [104.0], "close": [110.0], "atr_14": [5.0],
    })
    df = pl.concat([range_bars, breakout_row])
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_orb_sell_breakout_below_range() -> None:
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2)
    _feed_orb_bars(strat, range_bars)

    breakout_row = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [99.0], "low": [93.0], "close": [94.0], "atr_14": [5.0],
    })
    df = pl.concat([range_bars, breakout_row])
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_orb_only_one_signal_per_session() -> None:
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2)
    _feed_orb_bars(strat, range_bars)

    breakout = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [111.0], "low": [104.0], "close": [110.0], "atr_14": [5.0],
    })
    df1 = pl.concat([range_bars, breakout])
    sig1 = strat.on_candle("INFY", EQUITY, df1)
    assert sig1 is not None

    # Second breakout bar same session — should be ignored
    breakout2 = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC + timedelta(minutes=15)],
        "high": [115.0], "low": [108.0], "close": [114.0], "atr_14": [5.0],
    })
    df2 = pl.concat([df1, breakout2])
    sig2 = strat.on_candle("INFY", EQUITY, df2)
    assert sig2 is None


def test_orb_not_enough_bars_returns_none() -> None:
    strat = OpeningRangeBreakoutStrategy(orb_bars=4)
    # Only 1 bar — less than orb_bars+1=5
    df = pl.DataFrame({
        "timestamp": [_SESSION_OPEN_UTC],
        "high": [105.0], "low": [99.0], "close": [102.0], "atr_14": [5.0],
    })
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_orb_missing_atr_column_returns_none() -> None:
    strat = OpeningRangeBreakoutStrategy(orb_bars=1)
    df = pl.DataFrame({
        "timestamp": [_SESSION_OPEN_UTC, _POST_ORB_UTC],
        "high": [105.0, 110.0], "low": [99.0, 104.0], "close": [102.0, 110.0],
    })
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_orb_strategy_id() -> None:
    assert OpeningRangeBreakoutStrategy().id == "opening_range_breakout"


def test_orb_invalid_orb_bars_raises() -> None:
    with pytest.raises(ValueError):
        OpeningRangeBreakoutStrategy(orb_bars=0)


def test_orb_no_signal_on_nan_atr() -> None:
    """Covers line 98: null/NaN atr_14 on the last bar."""
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2)
    _feed_orb_bars(strat, range_bars)

    breakout = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [111.0], "low": [104.0], "close": [110.0], "atr_14": [float("nan")],
    })
    df = pl.concat([range_bars, breakout])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_orb_no_signal_when_range_not_established() -> None:
    """Covers line 144: or_high == 0.0 (range never accumulated)."""
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    # Feed a post-ORB bar directly without any range bars in state
    # Need height >= 3 so pad with dummy bars at same timestamp
    post_orb_bar = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [111.0], "low": [104.0], "close": [110.0], "atr_14": [5.0],
    })
    # Pad to meet height guard
    pad = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC, _POST_ORB_UTC],
        "high": [105.0, 105.0], "low": [99.0, 99.0], "close": [102.0, 102.0], "atr_14": [5.0, 5.0],
    })
    df = pl.concat([pad, post_orb_bar])
    # State is uninitialized for this symbol — or_high will be 0.0 after reset
    assert strat.on_candle("NEW_SYM", EQUITY, df) is None


def test_orb_no_signal_when_atr_zero_after_range() -> None:
    """Covers line 149: atr <= 0 when breakout bar has zero ATR."""
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2)
    _feed_orb_bars(strat, range_bars)

    breakout = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [111.0], "low": [104.0], "close": [110.0], "atr_14": [0.0],
    })
    df = pl.concat([range_bars, breakout])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_orb_no_signal_when_close_inside_range() -> None:
    """Covers line 189: close is between OR low and OR high — no breakout."""
    strat = OpeningRangeBreakoutStrategy(orb_bars=2)
    range_bars = _make_orb_bars(2, high=105.0, low=99.0)
    _feed_orb_bars(strat, range_bars)

    # Close inside range: 99 < 102 < 105
    inside_bar = pl.DataFrame({
        "timestamp": [_POST_ORB_UTC],
        "high": [104.0], "low": [100.0], "close": [102.0], "atr_14": [5.0],
    })
    df = pl.concat([range_bars, inside_bar])
    assert strat.on_candle("INFY", EQUITY, df) is None


# ---------------------------------------------------------------------------
# EmaCrossoverStrategy
# ---------------------------------------------------------------------------


def _df_with_ema(
    fast_vals: list[float],
    slow_vals: list[float],
    atr: float = 10.0,
) -> pl.DataFrame:
    n = len(fast_vals)
    return pl.DataFrame({
        "close": [100.0] * n,
        "ema_9": fast_vals,
        "ema_21": slow_vals,
        "atr_14": [atr] * n,
    })


def test_ema_buy_signal_on_golden_cross() -> None:
    strat = EmaCrossoverStrategy()
    # prev: fast < slow; cur: fast > slow → BUY
    df = _df_with_ema([19.0, 22.0], [20.0, 21.0])
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.BUY


def test_ema_sell_signal_on_death_cross() -> None:
    strat = EmaCrossoverStrategy()
    # prev: fast > slow; cur: fast < slow → SELL
    df = _df_with_ema([22.0, 19.0], [21.0, 20.0])
    sig = strat.on_candle("INFY", EQUITY, df)
    assert sig is not None
    assert sig.side == Side.SELL


def test_ema_no_signal_when_only_one_row() -> None:
    strat = EmaCrossoverStrategy()
    df = _df_with_ema([20.0], [21.0])
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_ema_no_signal_when_missing_column() -> None:
    strat = EmaCrossoverStrategy()
    df = pl.DataFrame({"close": [100.0, 101.0]})
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_ema_no_signal_when_atr_zero() -> None:
    strat = EmaCrossoverStrategy()
    df = _df_with_ema([19.0, 22.0], [20.0, 21.0], atr=0.0)
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_ema_invalid_params_raise() -> None:
    with pytest.raises(ValueError):
        EmaCrossoverStrategy(fast=21, slow=9)  # fast >= slow


def test_ema_strategy_id() -> None:
    assert EmaCrossoverStrategy().id == "ema_crossover"


def test_ema_get_state_before_any_candle() -> None:
    strat = EmaCrossoverStrategy()
    state = strat.get_state()
    assert state["ema_9"] is None
    assert state["ema_21"] is None


def test_ema_get_state_after_candle() -> None:
    strat = EmaCrossoverStrategy()
    df = _df_with_ema([19.0, 22.0], [20.0, 21.0])
    strat.on_candle("INFY", EQUITY, df)
    state = strat.get_state()
    assert state["ema_9"] == pytest.approx(22.0)


# ---------------------------------------------------------------------------
# Strategy.get_state default implementation
# ---------------------------------------------------------------------------


def test_strategy_base_get_state_default() -> None:
    """The default get_state() in Strategy base class returns {}."""
    class _Minimal(Strategy):
        @property
        def id(self) -> str:
            return "minimal"

        def on_candle(self, symbol, instrument_type, df):
            return None

    strat = _Minimal()
    assert strat.get_state() == {}


# ---------------------------------------------------------------------------
# Null/NaN column guards in RSI and VWAP
# ---------------------------------------------------------------------------


def test_rsi_no_signal_on_nan_column() -> None:
    strat = RsiMeanReversionStrategy()
    df = pl.DataFrame({
        "close": [100.0, 101.0],
        "rsi_14": [float("nan"), 32.0],
        "atr_14": [10.0, 10.0],
    })
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_vwap_no_signal_on_nan_column() -> None:
    strat = VwapReversionStrategy()
    df = pl.DataFrame({
        "close": [90.0, 92.0],
        "vwap": [float("nan"), 100.0],
        "atr_14": [10.0, 10.0],
    })
    assert strat.on_candle("INFY", EQUITY, df) is None


def test_ema_no_signal_on_nan_column() -> None:
    strat = EmaCrossoverStrategy()
    df = pl.DataFrame({
        "close": [100.0, 101.0],
        "ema_9": [float("nan"), 22.0],
        "ema_21": [20.0, 21.0],
        "atr_14": [10.0, 10.0],
    })
    assert strat.on_candle("INFY", EQUITY, df) is None
