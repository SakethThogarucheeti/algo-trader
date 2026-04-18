from __future__ import annotations

import math
from datetime import timedelta

import polars as pl

from testing.backtesting.portfolio import TradeRecord

# ---------------------------------------------------------------------------
# Pure metric functions — no side effects, no I/O.
#
# All functions accept the equity_curve DataFrame with columns:
#   date    — datetime
#   equity  — float
#
# and/or a list[TradeRecord].
# ---------------------------------------------------------------------------


def _returns(equity_curve: pl.DataFrame) -> pl.Series:
    """Compute period-over-period fractional returns from the equity curve."""
    eq = equity_curve["equity"]
    prev = eq.shift(1)
    return ((eq - prev) / prev).drop_nulls()


def sharpe_ratio(equity_curve: pl.DataFrame, risk_free_rate: float = 0.0) -> float:
    """
    Annualised Sharpe ratio.

    Uses simple period returns from the equity curve. The number of periods
    per year is inferred from the median gap between rows (falls back to 252
    trading-day equivalent if the curve has fewer than 2 rows).

    Returns 0.0 if there are insufficient data points or zero variance.
    """
    if len(equity_curve) < 2:
        return 0.0

    rets = _returns(equity_curve)
    if len(rets) == 0:
        return 0.0

    mean_ret = rets.mean()
    std_ret = rets.std()

    if std_ret is None or std_ret == 0.0:
        return 0.0

    # Estimate periods per year from median time gap
    periods_per_year = _periods_per_year(equity_curve)

    excess = float(mean_ret) - risk_free_rate / periods_per_year
    return float(excess / std_ret * math.sqrt(periods_per_year))


def max_drawdown(equity_curve: pl.DataFrame) -> float:
    """
    Maximum drawdown as a fraction in [0.0, 1.0].

    0.0 means no drawdown ever occurred; 1.0 means total ruin.
    """
    if len(equity_curve) < 2:
        return 0.0

    eq = equity_curve["equity"]
    running_max = eq.cum_max()
    drawdowns = (running_max - eq) / running_max
    return float(drawdowns.max() or 0.0)


def max_drawdown_duration(equity_curve: pl.DataFrame) -> timedelta:
    """
    Longest drawdown period (time from peak to recovery).

    Returns timedelta(0) if there are fewer than 2 rows or no drawdown.
    """
    if len(equity_curve) < 2:
        return timedelta(0)

    dates = equity_curve["date"].to_list()
    equities = equity_curve["equity"].to_list()

    peak_idx = 0
    peak_eq = equities[0]
    in_drawdown_since: int | None = None
    max_dur = timedelta(0)

    for i, (ts, eq) in enumerate(zip(dates, equities, strict=False)):
        if eq > peak_eq:
            if in_drawdown_since is not None:
                dur = ts - dates[in_drawdown_since]
                if dur > max_dur:
                    max_dur = dur
                in_drawdown_since = None
            peak_eq = eq
            peak_idx = i
        elif eq < peak_eq and in_drawdown_since is None:
            in_drawdown_since = peak_idx

    # If still in drawdown at the end
    if in_drawdown_since is not None:
        dur = dates[-1] - dates[in_drawdown_since]
        if dur > max_dur:
            max_dur = dur

    return max_dur


def win_rate(trades: list[TradeRecord]) -> float:
    """
    Fraction of trades that were profitable (pnl > 0).

    Returns 0.0 if there are no completed trades.
    """
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.pnl > 0)
    return wins / len(trades)


def profit_factor(trades: list[TradeRecord]) -> float:
    """
    Gross profit divided by gross loss.

    Returns float('inf') if there are no losing trades.
    Returns 0.0 if there are no winning trades.
    """
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))

    if gross_loss == 0.0:
        return float("inf") if gross_profit > 0 else 0.0
    if gross_profit == 0.0:
        return 0.0
    return gross_profit / gross_loss


def cagr(equity_curve: pl.DataFrame, initial_equity: float) -> float:
    """
    Compound annual growth rate.

    Returns 0.0 if the curve has fewer than 2 rows or time span is 0.
    """
    if len(equity_curve) < 2 or initial_equity <= 0:
        return 0.0

    dates = equity_curve["date"].to_list()
    final_eq = float(equity_curve["equity"][-1])

    years = (dates[-1] - dates[0]).total_seconds() / (365.25 * 86400)
    if years <= 0:
        return 0.0

    return (final_eq / initial_equity) ** (1.0 / years) - 1.0


def calmar_ratio(equity_curve: pl.DataFrame) -> float:
    """
    CAGR divided by maximum drawdown.

    Returns 0.0 if max drawdown is 0 or if CAGR cannot be computed.
    """
    if len(equity_curve) < 2:
        return 0.0

    initial_eq = float(equity_curve["equity"][0])
    _cagr = cagr(equity_curve, initial_eq)
    _mdd = max_drawdown(equity_curve)

    if _mdd == 0.0:
        return 0.0
    return _cagr / _mdd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _periods_per_year(equity_curve: pl.DataFrame) -> float:
    """Estimate number of periods per year from median bar gap. Default: 252."""
    if len(equity_curve) < 2:
        return 252.0

    dates = equity_curve["date"].to_list()
    gaps = [(dates[i + 1] - dates[i]).total_seconds() for i in range(len(dates) - 1)]
    if not gaps:
        return 252.0

    median_gap_secs = sorted(gaps)[len(gaps) // 2]
    if median_gap_secs <= 0:
        return 252.0

    return (365.25 * 86400) / median_gap_secs
