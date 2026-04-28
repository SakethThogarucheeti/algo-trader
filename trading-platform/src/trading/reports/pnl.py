"""FIFO matched-pair P&L computation."""

from __future__ import annotations

from collections import defaultdict

from trading.core.models import Signal
from trading.core.schemas import OrderStatus


def compute_pnl(signals: list[Signal]) -> dict[str, dict[str, float]]:
    """
    Compute realized P&L per (strategy_id, symbol) using FIFO matching.

    Returns a dict keyed by "strategy_id::symbol" with:
      realized  — total closed profit/loss
      open_qty  — net open quantity (positive = long, negative = short)
      open_avg  — average price of the open position (0 if flat)
    """
    fills: dict[tuple[str, str], list[tuple[str, int, float]]] = defaultdict(list)

    for sig in signals:
        for order in sig.orders:
            if order.status != OrderStatus.FILLED.value:
                continue
            fills[(sig.strategy_id, sig.symbol)].append(
                (sig.side, order.qty, float(order.avg_price))
            )

    results: dict[str, dict[str, float]] = {}
    for (strategy_id, symbol), trades in fills.items():
        long_queue: list[tuple[int, float]] = []
        short_queue: list[tuple[int, float]] = []
        realized = 0.0

        for side, qty, price in trades:
            if side == "BUY":
                remaining = qty
                while remaining > 0 and short_queue:
                    short_qty, short_price = short_queue[0]
                    matched = min(remaining, short_qty)
                    realized += matched * (short_price - price)
                    remaining -= matched
                    if matched == short_qty:
                        short_queue.pop(0)
                    else:
                        short_queue[0] = (short_qty - matched, short_price)
                if remaining > 0:
                    long_queue.append((remaining, price))
            else:  # SELL
                remaining = qty
                while remaining > 0 and long_queue:
                    long_qty, long_price = long_queue[0]
                    matched = min(remaining, long_qty)
                    realized += matched * (price - long_price)
                    remaining -= matched
                    if matched == long_qty:
                        long_queue.pop(0)
                    else:
                        long_queue[0] = (long_qty - matched, long_price)
                if remaining > 0:
                    short_queue.append((remaining, price))

        open_qty = sum(q for q, _ in long_queue) - sum(q for q, _ in short_queue)
        open_avg = (
            sum(q * p for q, p in long_queue) / sum(q for q, _ in long_queue)
            if long_queue
            else 0.0
        )
        results[f"{strategy_id}::{symbol}"] = {
            "realized": realized,
            "open_qty": float(open_qty),
            "open_avg": open_avg,
        }

    return results
