"""
Diagnostic test: run one EMA crossover combo, count signals on the bus,
then query audit_logs for rejection details.

Run with:
    cd trading-platform/strategy-testing
    uv run pytest strategy-testing/test_diagnose_signals.py -v -s
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from testing.backtesting.data_loader import FileDataLoader
from testing.backtesting.engine import BacktestSession
from testing.backtesting.report import BacktestConfig, BacktestReport

from trading.config.settings import AlgoSettings
from trading.core.messaging import MessageBus, RedisMessageBus
from trading.core.schemas import FillEvent, SignalEvent, ValidatedOrderEvent

_DATA_DIR = Path(__file__).parents[2] / "data"

pytestmark = pytest.mark.skipif(
    not _DATA_DIR.exists(),
    reason="data/ directory not found — run uv run fetch-data first",
)

_SCHEMA = "bt_diag_9_21_1_5"
_END = datetime(2026, 4, 17, tzinfo=UTC)
_START = _END - timedelta(days=30)
_EQUITY = 10_000.0
_INTERVAL = "15min"
_SYMBOLS = ["INFY", "TCS", "RELIANCE", "HDFCBANK", "ICICIBANK"]


async def test_diagnose_signal_flow(pg_engine, redis_client, tmp_path):
    """
    Tap the bus to count signals generated vs validated vs filled,
    then read audit_logs for every rejection reason.
    """
    bus = RedisMessageBus(redis_client)

    signals_generated: list[SignalEvent] = []
    orders_validated: list[ValidatedOrderEvent] = []
    fills_received: list[FillEvent] = []

    signals_channel = f"signals:{_SCHEMA}"
    validated_channel = f"validated_orders:{_SCHEMA}"

    # Index signals by id so we can look them up when reading audit rejections
    signals_by_id: dict[str, SignalEvent] = {}

    def _record_signal(s: SignalEvent) -> None:
        signals_generated.append(s)
        signals_by_id[str(s.signal_id)] = s

    bus.subscribe(signals_channel, SignalEvent, _record_signal)
    bus.subscribe(validated_channel, ValidatedOrderEvent, orders_validated.append)
    bus.subscribe("fills", FillEvent, fills_received.append)

    config = BacktestConfig(
        algo=AlgoSettings(
            name=_SCHEMA,
            instruments=_SYMBOLS,
            strategy_id="ema_crossover",
            candle_intervals=[_INTERVAL],
            equity=_EQUITY,
        ),
        start=_START,
        end=_END,
        loader=FileDataLoader(_DATA_DIR),
        initial_equity=_EQUITY,
        slippage_pct=0.05,
        strategy_params={"fast": 9, "slow": 21, "atr_multiplier": 1.5},
        feature_engine_params={"ema_spans": (9, 21)},
    )

    session = BacktestSession(
        config=config,
        db_engine=pg_engine,
        redis=redis_client,
        bus=bus,
        results_dir=tmp_path,
        db_schema=_SCHEMA,
        keep_schema=True,
    )
    report: BacktestReport = await session.run()

    # ------------------------------------------------------------------
    # Bus-level counts
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Trades: {report.total_trades}  Final equity: {report.final_equity:,.0f}")
    print(f"{'='*60}")
    print("\n--- bus event counts ---")
    print(f"  signals generated : {len(signals_generated)}")
    print(f"  orders validated  : {len(orders_validated)}")
    print(f"  fills received    : {len(fills_received)}")

    if signals_generated:
        by_symbol: dict[str, int] = defaultdict(int)
        by_side: dict[str, int] = defaultdict(int)
        for s in signals_generated:
            by_symbol[s.symbol] += 1
            by_side[s.side.value] += 1
        print("\n--- signals by symbol ---")
        for sym, cnt in sorted(by_symbol.items()):
            print(f"  {sym:<12} {cnt}")
        print("\n--- signals by side ---")
        for side, cnt in sorted(by_side.items()):
            print(f"  {side:<8} {cnt}")

    # ------------------------------------------------------------------
    # audit_logs from DB
    # ------------------------------------------------------------------
    async with pg_engine.connect() as conn:
        await conn.execute(text(f'SET search_path TO "{_SCHEMA}"'))

        rows = (await conn.execute(
            text("SELECT module, level, message FROM audit_logs ORDER BY created_at")
        )).fetchall()

        print(f"\n--- audit_logs ({len(rows)} rows, rejections only) ---")
        reason_counts: dict[str, int] = defaultdict(int)
        for r in rows:
            if "rejected:" not in r.message:
                continue
            reason = r.message.split("rejected:")[-1].strip()
            reason_counts[reason] += 1
            # Extract signal id from message: "signal <uuid> rejected: REASON"
            parts = r.message.split()
            sig_id = parts[1] if len(parts) > 1 else ""
            sig = signals_by_id.get(sig_id)
            sig_info = f"{sig.symbol} {sig.side.value}" if sig else "unknown"
            print(f"  {reason:<24} {sig_info}")


        if reason_counts:
            print("\n--- rejection reason counts ---")
            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                print(f"  {reason:<30} {count}")

    # Clean up
    async with pg_engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))

    print(f"{'='*60}\n")
