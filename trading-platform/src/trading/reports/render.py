"""Formatting helpers and report section renderers."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from trading.core.models import AuditLog, DecisionLog, Heartbeat, Signal
from trading.core.schemas import OrderStatus
from trading.reports.pnl import compute_pnl


_W = 70


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def hr(char: str = "─") -> None:
    print(char * _W)


def section(title: str) -> None:
    print()
    hr("═")
    print(f"  {title}")
    hr("═")


def subsection(title: str) -> None:
    print()
    print(f"  ── {title}")
    hr()


def row(label: str, value: object, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{label:<36}{value}")


def pnl_str(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def print_strategy_section(
    signals: list[Signal],
    decisions: list[DecisionLog],
    algo_configs: list[dict[str, object]],
) -> None:
    section("STRATEGY PERFORMANCE")

    # --- Signal funnel ---
    subsection("Signal Funnel")

    step_counts: dict[str, int] = defaultdict(int)
    rejection_reasons: dict[str, int] = defaultdict(int)
    for d in decisions:
        step_counts[d.step] += 1
        if d.step == "SIGNAL_REJECTED":
            ctx = json.loads(d.context) if d.context else {}
            rejection_reasons[str(ctx.get("reason", "UNKNOWN"))] += 1

    generated = step_counts.get("SIGNAL_GENERATED", 0)
    accepted = step_counts.get("SIGNAL_ACCEPTED", 0)
    rejected = step_counts.get("SIGNAL_REJECTED", 0)
    acceptance_rate = (accepted / generated * 100) if generated else 0.0

    row("Candles emitted", step_counts.get("CANDLE_EMITTED", 0))
    row("Signals generated", generated)
    row("  Accepted", accepted)
    row("  Rejected", rejected)
    row("Acceptance rate", f"{acceptance_rate:.1f}%")

    if rejection_reasons:
        print()
        print("    Rejection breakdown:")
        for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
            print(f"      {reason:<32}{count}")

    # --- Order funnel ---
    subsection("Order Funnel")

    all_orders = [o for s in signals for o in s.orders]
    by_status: dict[str, int] = defaultdict(int)
    for o in all_orders:
        by_status[o.status] += 1

    total_orders = len(all_orders)
    filled = by_status.get(OrderStatus.FILLED.value, 0)
    fill_rate = (filled / total_orders * 100) if total_orders else 0.0

    row("Orders placed", total_orders)
    row("  Filled", filled)
    row("  Rejected by broker", by_status.get(OrderStatus.REJECTED.value, 0))
    row("  Cancelled", by_status.get(OrderStatus.CANCELLED.value, 0))
    row("Fill rate", f"{fill_rate:.1f}%")

    # --- Per-symbol trade summary ---
    subsection("Trades by Symbol")

    symbol_data: dict[str, dict[str, object]] = defaultdict(
        lambda: {"buys": 0, "sells": 0, "volume": 0, "gross": 0.0}
    )
    for sig in signals:
        for order in sig.orders:
            if order.status != OrderStatus.FILLED.value:
                continue
            d = symbol_data[sig.symbol]
            if sig.side == "BUY":
                d["buys"] = int(d["buys"]) + 1  # type: ignore[arg-type]
                d["gross"] = float(d["gross"]) - order.qty * float(order.avg_price)
            else:
                d["sells"] = int(d["sells"]) + 1  # type: ignore[arg-type]
                d["gross"] = float(d["gross"]) + order.qty * float(order.avg_price)
            d["volume"] = int(d["volume"]) + order.qty

    if symbol_data:
        print(f"    {'Symbol':<16}{'Buys':>6}{'Sells':>6}{'Volume':>10}{'Cash Flow':>14}")
        hr()
        for symbol, d in sorted(symbol_data.items()):
            print(
                f"    {symbol:<16}{d['buys']:>6}{d['sells']:>6}"
                f"{d['volume']:>10}{pnl_str(float(d['gross'])):>14}"  # type: ignore[arg-type]
            )
    else:
        print("    No filled orders in this period.")

    # --- P&L ---
    subsection("Realized P&L (FIFO matched)")

    pnl_map = compute_pnl(signals)
    total_realized = 0.0

    if pnl_map:
        print(f"    {'Position':<36}{'Realized':>12}{'Open Qty':>10}{'Open Avg':>12}")
        hr()
        for label, data in sorted(pnl_map.items()):
            r = data["realized"]
            total_realized += r
            open_qty = int(data["open_qty"])
            open_avg = data["open_avg"]
            print(
                f"    {label:<36}{pnl_str(r):>12}"
                f"{str(open_qty) if open_qty else '—':>10}"
                f"{f'{open_avg:.2f}' if open_qty else '—':>12}"
            )
        hr()
        print(f"    {'TOTAL':<36}{pnl_str(total_realized):>12}")
    else:
        print("    No matched trades in this period.")

    # --- Algo configuration snapshot ---
    subsection("Algo Configuration")

    if algo_configs:
        for cfg in algo_configs:
            status = "enabled" if cfg["enabled"] else "DISABLED"
            state = cfg["state"]
            bars_seen = state.get("bars_seen", "?")  # type: ignore[union-attr]
            warmup_complete = state.get("warmup_complete", False)  # type: ignore[union-attr]
            warmup_str = "complete" if warmup_complete else f"{bars_seen}/{cfg['warmup_candles']} bars"
            params_str = ", ".join(f"{k}={v}" for k, v in cfg["params"].items())  # type: ignore[union-attr]
            print(f"    {cfg['name']} [{status}]")
            print(f"      strategy: {cfg['strategy_id']}  equity: {cfg['equity']:,.0f}")
            print(f"      warmup: {warmup_str}")
            if params_str:
                print(f"      params: {params_str}")
    else:
        print("    No algo configs found.")


def print_system_section(
    decisions: list[DecisionLog],
    audit_logs: list[AuditLog],
    heartbeats: list[Heartbeat],
) -> None:
    section("SYSTEM PERFORMANCE")

    # --- Pipeline throughput ---
    subsection("Pipeline Throughput")

    step_counts: dict[str, int] = defaultdict(int)
    for d in decisions:
        step_counts[d.step] += 1

    row("Candles emitted", step_counts.get("CANDLE_EMITTED", 0))
    row("Decisions logged", len(decisions))

    algo_candles: dict[str, int] = defaultdict(int)
    for d in decisions:
        if d.step == "CANDLE_EMITTED" and d.algo_name:
            algo_candles[d.algo_name] += 1
    if algo_candles:
        print()
        print("    Candles per algo:")
        for algo, count in sorted(algo_candles.items()):
            print(f"      {algo:<30}{count}")

    # --- Heartbeat status ---
    subsection("Module Heartbeat Status")

    cutoff_live = datetime.now(UTC) - timedelta(minutes=5)

    if heartbeats:
        print(f"    {'Module':<28}{'Last Seen (UTC)':>28}{'Status':>10}")
        hr()
        for hb in heartbeats:
            last = hb.last_seen
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            status = "OK" if last >= cutoff_live else "STALE"
            print(f"    {hb.module:<28}{last.strftime('%Y-%m-%d %H:%M:%S'):>28}{status:>10}")
    else:
        print("    No heartbeat records found.")

    # --- Audit log summary ---
    subsection("Audit Log Summary")

    by_level: dict[str, list[AuditLog]] = defaultdict(list)
    for entry in audit_logs:
        by_level[entry.level].append(entry)

    row("Total entries", len(audit_logs))
    for level in ("ERROR", "WARNING", "INFO"):
        row(f"  {level}", len(by_level.get(level, [])))

    for level, limit in (("ERROR", 10), ("WARNING", 5)):
        entries = by_level.get(level, [])
        if entries:
            print()
            print(f"    {level.capitalize()}s:")
            for entry in entries[:limit]:
                ts = entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
                print(f"      [{ts}] {entry.module}: {entry.message[:60]}")
            if len(entries) > limit:
                print(f"      ... and {len(entries) - limit} more")

    # --- Risk controller summary ---
    subsection("Risk Controller Activity")

    risk_hits: dict[str, int] = defaultdict(int)
    circuit_events = 0
    for d in decisions:
        if d.step == "SIGNAL_REJECTED":
            ctx = json.loads(d.context) if d.context else {}
            reason = str(ctx.get("reason", "UNKNOWN"))
            risk_hits[reason] += 1
            if reason == "CIRCUIT_OPEN":
                circuit_events += 1

    if risk_hits:
        print(f"    {'Rejection Reason':<32}{'Count':>8}")
        hr()
        for reason, count in sorted(risk_hits.items(), key=lambda x: -x[1]):
            print(f"    {reason:<32}{count:>8}")
        if circuit_events:
            print(f"\n    Circuit breaker fired {circuit_events} time(s) in this period.")
    else:
        print("    No risk rejections in this period.")
