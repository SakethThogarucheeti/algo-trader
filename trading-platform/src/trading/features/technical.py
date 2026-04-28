from __future__ import annotations

import logging
from datetime import time

import polars as pl

from trading.core.schemas import CandleEvent
from trading.features.base import FeatureEngine

logger = logging.getLogger(__name__)

# Session open in IST — VWAP resets at 09:15
_SESSION_OPEN_IST = time(9, 15)
_IST_OFFSET_MINS = 5 * 60 + 30  # +05:30


_DEFAULT_EMA_SPANS = (9, 21)
_DEFAULT_ATR_PERIOD = 14
_DEFAULT_RSI_PERIOD = 14


class TechnicalFeatureEngine(FeatureEngine):
    """
    Maintains a rolling Polars DataFrame per (symbol, interval) and
    computes technical indicators on each update.

    Indicators: ema_{n}, rsi_14, atr_{n}, vwap. All null while warming up.
    No TA-Lib — computed with Polars expressions only.

    Parameters
    ----------
    window_size:
        Maximum number of bars to retain in memory per (symbol, interval).
    ema_spans:
        EMA periods to compute. Default: (9, 21).
    atr_period:
        ATR smoothing period. Default: 14.
    """

    alias = "technical"

    def __init__(
        self,
        window_size: int = 200,
        ema_spans: tuple[int, ...] | list[int] = _DEFAULT_EMA_SPANS,
        atr_period: int = _DEFAULT_ATR_PERIOD,
    ) -> None:
        self._window_size = window_size
        self._ema_spans: tuple[int, ...] = tuple(ema_spans)
        self._atr_period = atr_period
        # (symbol, interval) → rolling DataFrame
        self._frames: dict[tuple[str, str], pl.DataFrame] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, event: CandleEvent) -> pl.DataFrame:
        """Append *event* to the rolling window and recompute indicators."""
        key = (event.symbol, event.interval)
        new_row = pl.DataFrame(
            {
                "timestamp": [event.timestamp],
                "open": [event.open],
                "high": [event.high],
                "low": [event.low],
                "close": [event.close],
                "volume": [event.volume],
            },
            schema={
                "timestamp": pl.Datetime("us", "UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Int64,
            },
        )

        existing = self._frames.get(key)
        if existing is None:
            df = new_row
        else:
            _base_cols = ("timestamp", "open", "high", "low", "close", "volume")
            indicator_cols = [c for c in existing.columns if c not in _base_cols]
            base = existing.drop(indicator_cols) if indicator_cols else existing
            df = pl.concat([base, new_row], how="vertical")

        # Trim to window_size
        if df.height > self._window_size:
            df = df.tail(self._window_size)

        df = _add_indicators(df, ema_spans=self._ema_spans, atr_period=self._atr_period)
        self._frames[key] = df
        logger.debug(
            "TechnicalFeatureEngine: %s/%s updated rows=%d",
            event.symbol,
            event.interval,
            df.height,
        )
        return df

    def get(self, symbol: str, interval: str) -> pl.DataFrame | None:
        """Return current DataFrame without updating."""
        return self._frames.get((symbol, interval))


# ---------------------------------------------------------------------------
# Indicator computation (pure functions, split into two passes)
# ---------------------------------------------------------------------------


def _add_indicators(
    df: pl.DataFrame,
    ema_spans: tuple[int, ...] = _DEFAULT_EMA_SPANS,
    atr_period: int = _DEFAULT_ATR_PERIOD,
) -> pl.DataFrame:
    """
    Two-pass indicator computation:
    1. Add ``_session_id`` (materialised column needed by VWAP ``over``).
    2. Compute all indicators.
    """
    # --- Pass 1: session ID for VWAP grouping ---
    ist_minutes = (
        pl.col("timestamp").dt.hour() * 60 + pl.col("timestamp").dt.minute() + _IST_OFFSET_MINS
    ) % (24 * 60)

    session_open_min = _SESSION_OPEN_IST.hour * 60 + _SESSION_OPEN_IST.minute

    # Row is a new session when the *date* changes or IST time == 09:15.
    # fill_null(True) so the very first row always starts session 1.
    new_date = (pl.col("timestamp").dt.date() != pl.col("timestamp").dt.date().shift(1)).fill_null(
        True
    )
    at_open = ist_minutes == session_open_min
    is_new_session = new_date | at_open

    df = df.with_columns(is_new_session.cast(pl.Int64).cum_sum().alias("_session_id"))

    # --- Pass 2: compute all indicators ---
    indicator_exprs = [
        *[_ema(span).alias(f"ema_{span}") for span in ema_spans],
        _rsi(_DEFAULT_RSI_PERIOD).alias(f"rsi_{_DEFAULT_RSI_PERIOD}"),
        _atr(atr_period).alias(f"atr_{atr_period}"),
        _vwap().alias("vwap"),
    ]
    df = df.with_columns(indicator_exprs).drop("_session_id")

    return df


def _ema(span: int) -> pl.Expr:
    """Exponential Moving Average with *span* periods (Wilder-style, adjust=False)."""
    return pl.col("close").ewm_mean(span=span, adjust=False)


def _rsi(period: int) -> pl.Expr:
    """
    RSI using Wilder smoothing (EWM alpha=1/period, adjust=False).

    fill_null(0) on the first diff so the seed value for EWM is 0.
    Returns NaN-like values while data is insufficient (denominator → 0).
    """
    delta = pl.col("close").diff().fill_null(0.0)
    gain = delta.clip(lower_bound=0.0)
    loss = (-delta).clip(lower_bound=0.0)
    avg_gain = gain.ewm_mean(alpha=1.0 / period, adjust=False)
    avg_loss = loss.ewm_mean(alpha=1.0 / period, adjust=False)
    rs = avg_gain / avg_loss  # → inf or NaN when avg_loss == 0
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # NaN arises when avg_gain==avg_loss==0 (no movement); treat as undefined
    return rsi.fill_nan(None)


def _atr(period: int) -> pl.Expr:
    """
    Average True Range using Wilder smoothing.

    True Range = max(high-low, |high-prev_close|, |low-prev_close|).
    First row uses high-low (prev_close filled with current close so gaps = 0).
    """
    prev_close = pl.col("close").shift(1).fill_null(pl.col("close"))
    tr = pl.max_horizontal(
        pl.col("high") - pl.col("low"),
        (pl.col("high") - prev_close).abs(),
        (pl.col("low") - prev_close).abs(),
    )
    return tr.ewm_mean(alpha=1.0 / period, adjust=False)


def _vwap() -> pl.Expr:
    """
    Cumulative VWAP grouped by ``_session_id`` (added in Pass 1).

    Returns null when cumulative volume is 0 to avoid division by zero.
    """
    tv = pl.col("close") * pl.col("volume").cast(pl.Float64)
    cum_tv = tv.cum_sum().over("_session_id")
    cum_vol = pl.col("volume").cast(pl.Float64).cum_sum().over("_session_id")
    return cum_tv / cum_vol
