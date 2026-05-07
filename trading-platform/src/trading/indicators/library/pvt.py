"""Price Volume Trend (z-scored) — cumulative volume-weighted price change."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from trading.indicators.base import Indicator, IndicatorParameters

if TYPE_CHECKING:
    from trading.indicators.store import CandleStore


class PVT(Indicator):
    """
    Price Volume Trend, z-scored over a rolling window.

    Raw PVT (cumulative) = sum of (close_pct_change_i * volume_i).
    Z-score = (raw_pvt - mean(raw_pvt_window)) / std(raw_pvt_window)

    Extreme z-scores signal that cumulative volume-weighted buying/selling
    pressure is at a multi-period extreme — a potential mean-reversion setup.

    Returns z-score (float); returns None when fewer than *period* + 1 bars
    are available or std of the window is zero.
    """

    class Parameters(IndicatorParameters):
        period: int = Field(default=20, ge=4)

    alias = "pvt"

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None:
        super().__init__(store, symbol, interval)

    async def compute(self, params: Parameters) -> float | None:  # type: ignore[override]
        # Need period+1 bars to compute period pct-changes, then z-score
        rows = await self._store.fetch(self._symbol, self._interval, params.period + 1)
        if len(rows) < params.period + 1:
            return None

        closes = np.array([r["close"] for r in rows], dtype=float)
        volumes = np.array([r["volume"] for r in rows], dtype=float)

        pct_changes = np.diff(closes) / closes[:-1]  # length == period
        pct_changes = np.where(np.isfinite(pct_changes), pct_changes, 0.0)

        # Cumulative PVT values for each step in the window
        raw_pvt = np.cumsum(pct_changes * volumes[1:])

        std = float(np.std(raw_pvt, ddof=1))
        if std == 0.0:
            return None

        mean = float(np.mean(raw_pvt))
        return float((raw_pvt[-1] - mean) / std)

    def __repr__(self) -> str:
        return "PVT()"
