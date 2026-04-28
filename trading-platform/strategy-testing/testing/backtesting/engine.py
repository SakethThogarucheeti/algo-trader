from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from testing.backtesting.data_loader import DataLoader
from testing.local_bus import LocalMessageBus
from testing.backtesting.metrics import (
    cagr,
    calmar_ratio,
    max_drawdown,
    max_drawdown_duration,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
from testing.backtesting.portfolio import EquityTracker
from testing.backtesting.report import BacktestConfig, BacktestReport
from testing.registry import session_type
from testing.session import SessionProgressEvent, TestingSession
from testing.simulators.execution_sim import SlippageFillSimulator
from trading.broker.paper_broker import PriceStore
from trading.config.settings import Settings
from trading.core.clock import SimulatedClock
from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus
from trading.core.schemas import FillEvent, InstrumentType, Side
from trading.data.candles import _SymbolConfig
from trading.di.providers.execution import make_execution_engine
from trading.di.providers.features import make_feature_engine
from trading.di.providers.risk import make_risk_controller
from trading.di.providers.strategy import make_strategy
from trading.engine.algo_runner import AlgoRunner
from trading.engine.runtime import Runtime
from trading.execution.executor import OrderExecutor
from trading.storage.repository import Repository

logger = logging.getLogger(__name__)


@session_type("backtest")
class BacktestSession(TestingSession):
    """
    Full backtest session.

    Reuses live components (AlgoRunner → RiskController → DirectExecutionEngine)
    driven by CandlePlayer instead of a live broker stream. The only replaced
    component is the Broker: ``SlippageFillSimulator`` replaces ``ZerodhaBroker``.

    Components start in the same order as live trading, giving identical
    signal/risk/execution logic — the only difference is the data source.
    """

    _config_cls = BacktestConfig

    def __init__(
        self,
        config: BacktestConfig,
        db_engine: AsyncEngine,
        redis: Redis,
        bus: MessageBus,
        results_dir: Path,
        db_schema: str = "public",
        keep_schema: bool = False,
    ) -> None:
        super().__init__(bus=bus, results_dir=results_dir)
        self._config = config
        self._db_engine = db_engine
        self._redis = redis
        self._db_schema = db_schema
        self._keep_schema = keep_schema

    async def run(self) -> BacktestReport:
        config = self._config
        session_id = config.session_id or str(uuid.uuid4())
        config.session_id = session_id
        started_at = self._now()

        logger.info(
            "BacktestSession[%s]: starting  algo=%s  start=%s  end=%s  equity=%.0f",
            self._db_schema, config.algo.name,
            config.start.date(), config.end.date(), config.initial_equity,
        )

        # Replace the Redis-backed bus with an in-process bus for this backtest.
        # All component wiring happens locally — no Redis round-trips per bar.
        self._bus = LocalMessageBus()

        partial_report: BacktestReport | None = None
        schema_engine = None
        tracker = EquityTracker(config.initial_equity)

        try:
            # ------------------------------------------------------------------
            # 1. Infrastructure — schema-isolated engine for parallel safety
            # ------------------------------------------------------------------
            schema_engine = await _make_schema_engine(self._db_engine, self._db_schema)
            sf = build_session_factory(schema_engine)
            await init_db(schema_engine)
            repo = Repository()
            logger.debug("BacktestSession[%s]: DB schema ready", self._db_schema)

            # ------------------------------------------------------------------
            # 2. Simulator broker + price store
            # ------------------------------------------------------------------
            price_store = PriceStore()
            simulator = SlippageFillSimulator(
                price_store=price_store,
                slippage_pct=config.slippage_pct,
                partial_fill_prob=config.partial_fill_prob,
                latency_secs=config.latency_secs,
            )

            # ------------------------------------------------------------------
            # 3. Load OHLCV data (raises FileNotFoundError / ValueError early)
            # ------------------------------------------------------------------
            algo = config.algo
            intervals = algo.candle_intervals or ["1min", "5min", "15min"]
            symbol_configs = [
                _SymbolConfig(
                    symbol=s,
                    instrument_token=0,
                    instrument_type=InstrumentType.EQUITY,
                )
                for s in algo.instruments
            ]
            data = _load_data(config.loader, algo.instruments, intervals, config.start, config.end)

            # Pre-populate price store with first known prices
            for (sym, _), df in data.items():
                if len(df) > 0:
                    price_store.update(sym, float(df["close"][0]))

            # ------------------------------------------------------------------
            # 4. Simulated clock + synthetic Settings
            #    The clock is advanced at each candle bar so the risk controller
            #    sees the bar's timestamp (not wall clock) for the time cutoff.
            # ------------------------------------------------------------------
            sim_clock = SimulatedClock()
            synthetic_settings = _make_backtest_settings()

            # ------------------------------------------------------------------
            # 5. Channel names + fill tracking
            # ------------------------------------------------------------------
            signals_channel = f"signals:{algo.name}"
            validated_orders_channel = f"validated_orders:{algo.name}"
            orders_channel = f"orders:{algo.name}"
            fills_channel = f"fills:{algo.name}"

            # Register the kite_order_id→(symbol, side) mapping synchronously
            # inside the executor, before any FillEvent is published.  This
            # avoids the pub/sub race where on_fill_event arrived before the
            # _on_order bus handler had a chance to call record_order().
            def _on_order_placed(kite_order_id: str, symbol: str, side: Side) -> None:
                tracker.record_order(kite_order_id, symbol, side)

            self._bus.subscribe(fills_channel, FillEvent, tracker.on_fill_event)

            # ------------------------------------------------------------------
            # 6. Build components
            # ------------------------------------------------------------------

            algo_runner = AlgoRunner(
                bus=self._bus,
                algo_name=algo.name,
                symbols=algo.instruments,
                instrument_types={s: InstrumentType.EQUITY for s in algo.instruments},
                intervals=intervals,
                strategy=make_strategy(algo.strategy_id, config.strategy_params or None),
                feature_engine=make_feature_engine(
                    algo.feature_engine_id, config.feature_engine_params or None
                ),
                session_factory=sf,
                repo=repo,
            )

            risk_controller = make_risk_controller(
                algo.risk_controller_id,
                bus=self._bus,
                repo=repo,
                sf=sf,
                settings=synthetic_settings,
                equity=config.initial_equity,
                signals_channel=signals_channel,
                validated_orders_channel=validated_orders_channel,
                clock=sim_clock,
            )

            execution_engine = make_execution_engine(
                algo.execution_engine_id,
                bus=self._bus,
                broker=simulator,
                repo=repo,
                sf=sf,
                price_store=price_store,
                orders_channel=orders_channel,
                fills_channel=fills_channel,
                on_order_placed=_on_order_placed,
            )

            order_executor = OrderExecutor(
                bus=self._bus,
                execution_engine=execution_engine,
                channel=validated_orders_channel,
            )

            # ------------------------------------------------------------------
            # 7. CandlePlayer
            # ------------------------------------------------------------------
            total_bars = sum(len(df) for df in data.values())
            bars_done: list[int] = [0]
            _last_snapshot_ts: list[datetime | None] = [None]

            async def _on_progress(n: int, bar_ts: datetime) -> None:
                bars_done[0] = n
                pct = n / total_bars if total_bars > 0 else 1.0
                await self._emit_progress(
                    SessionProgressEvent(
                        session_id=session_id,
                        session_type="backtest",
                        pct_complete=pct,
                        bars_processed=n,
                        signals_generated=0,
                        timestamp=self._now(),
                    )
                )
                # Advance the simulated clock so the risk controller sees the
                # bar's timestamp for the intraday cutoff check.
                sim_clock.advance(bar_ts)
                # Snapshot equity at each unique bar timestamp so the equity
                # curve is a properly-dated daily series (not wall-clock stamped).
                # Multiple symbols share a timestamp; snapshot once per unique ts.
                if bar_ts != _last_snapshot_ts[0]:
                    tracker.snapshot(bar_ts)
                    _last_snapshot_ts[0] = bar_ts

            from testing.simulators.candle_player import CandlePlayer

            runtime = Runtime(
                [
                    algo_runner,
                    risk_controller,
                    order_executor,
                ]
            )

            candle_player = CandlePlayer(
                symbols=symbol_configs,
                intervals=intervals,
                start=config.start,
                end=config.end,
                runtime=runtime,
                bus=self._bus,
                on_progress=_on_progress,
                data=data,
                replay_delay_secs=config.replay_delay_secs,
                on_bar_price=price_store.update,
            )

            # ------------------------------------------------------------------
            # 8. Run — CandlePlayer calls runtime.stop() when replay is done
            # ------------------------------------------------------------------
            import anyio

            async with anyio.create_task_group() as tg:
                tg.start_soon(candle_player.start)
                tg.start_soon(runtime.start)

            # ------------------------------------------------------------------
            # 9. Close open positions + compute metrics
            # ------------------------------------------------------------------
            last_prices: dict[str, float] = {s: price_store.get(s) or 0.0 for s in algo.instruments}
            tracker.close_open_positions(last_prices)

            eq_curve = tracker.equity_curve
            trades = tracker.trades

            report = BacktestReport(
                config=config,
                equity_curve=eq_curve,
                trades=trades,
                sharpe_ratio=sharpe_ratio(eq_curve),
                max_drawdown=max_drawdown(eq_curve),
                max_drawdown_duration=max_drawdown_duration(eq_curve),
                win_rate=win_rate(trades),
                profit_factor=profit_factor(trades),
                cagr=cagr(eq_curve, config.initial_equity, start=config.start, end=config.end),
                calmar_ratio=calmar_ratio(eq_curve, start=config.start, end=config.end),
                total_trades=len(trades),
                final_equity=tracker.current_equity,
                session_id=session_id,
                session_type="backtest",
                started_at=started_at,
                finished_at=self._now(),
            )
            partial_report = report
            logger.info(
                "BacktestSession[%s]: complete  trades=%d  sharpe=%.3f  pnl=%+.0f"
                "  win_rate=%.0f%%  max_dd=%.1f%%  equity=%.0f",
                self._db_schema,
                report.total_trades,
                report.sharpe_ratio,
                report.final_equity - config.initial_equity,
                report.win_rate * 100,
                report.max_drawdown * 100,
                report.final_equity,
            )
            return report

        finally:
            if partial_report is not None:
                await self._persist(partial_report)
            if schema_engine is not None:
                if not self._keep_schema:
                    await _drop_schema(self._db_engine, self._db_schema)
                await schema_engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_data(
    loader: DataLoader,
    symbols: list[str],
    intervals: list[str],
    start: datetime,
    end: datetime,
) -> dict[tuple[str, str], object]:
    """Load all symbol × interval combinations upfront."""
    import polars as pl

    data: dict[tuple[str, str], pl.DataFrame] = {}
    for symbol in symbols:
        for interval in intervals:
            try:
                df = loader.load(symbol, interval, start, end)
                data[(symbol, interval)] = df
            except FileNotFoundError:
                logger.warning("BacktestSession: no data for %s/%s — skipping", symbol, interval)
    return data


# Intra-process lock: serializes DDL coroutines within the same process.
_schema_create_lock = asyncio.Lock()


async def _make_schema_engine(base_engine: AsyncEngine, schema: str) -> AsyncEngine:
    """
    Create (or reset) a Postgres schema and return an engine whose connections
    have ``search_path`` pinned to that schema.

    DDL is serialized via a process-level asyncio.Lock. Run grid searches
    sequentially (one pytest process at a time) to avoid cross-process catalog
    deadlocks — Postgres cannot serialize DDL across separate OS processes.
    """
    async with _schema_create_lock:
        async with base_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    return create_async_engine(
        base_engine.url,
        echo=False,
        connect_args={
            "server_settings": {"search_path": schema},
            "prepared_statement_cache_size": 0,
        },
    )


async def _drop_schema(base_engine: AsyncEngine, schema: str) -> None:
    """Drop the isolated schema after the session completes."""
    if schema == "public":
        return  # never drop the default schema

    async with _schema_create_lock:
        async with base_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _make_backtest_settings() -> Settings:
    """
    Create a synthetic Settings object for use in backtesting.

    Sets intraday cutoff to 23:59 (effectively disabled) and paper_trading=True
    so the risk controller does not apply the circuit breaker or daily time cutoff.
    """

    # We must satisfy pydantic-settings validation; provide dummy values for
    # required broker credentials and URLs.
    return Settings(
        zerodha_api_key="BACKTEST",
        zerodha_api_secret="BACKTEST",
        zerodha_access_token="BACKTEST",
        postgres_url="postgresql+asyncpg://user:pass@localhost/backtest",
        redis_url="redis://localhost:6379/0",
        intraday_cutoff_hour=23,
        intraday_cutoff_minute=59,
        paper_trading=True,
    )
