from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from testing.backtesting.data_loader import DataLoader
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
from trading.core.database import build_session_factory, init_db
from trading.core.messaging import MessageBus
from trading.core.schemas import FillEvent, InstrumentType, OrderEvent, Side, ValidatedOrderEvent
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
    ) -> None:
        super().__init__(bus=bus, results_dir=results_dir)
        self._config = config
        self._db_engine = db_engine
        self._redis = redis

    async def run(self) -> BacktestReport:
        config = self._config
        session_id = config.session_id or str(uuid.uuid4())
        config.session_id = session_id
        started_at = self._now()

        partial_report: BacktestReport | None = None
        tracker = EquityTracker(config.initial_equity)

        try:
            # ------------------------------------------------------------------
            # 1. Infrastructure
            # ------------------------------------------------------------------
            sf = build_session_factory(self._db_engine)
            await init_db(self._db_engine)  # idempotent in tests
            repo = Repository()

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
            # 4. Synthetic Settings for risk controller (no time cutoff, paper mode)
            # ------------------------------------------------------------------
            synthetic_settings = _make_backtest_settings()

            # ------------------------------------------------------------------
            # 5. Subscribe to fills for equity tracking
            # ------------------------------------------------------------------
            signals_channel = f"signals:{algo.name}"
            validated_orders_channel = f"validated_orders:{algo.name}"

            # Correlate: signal_id → (symbol, side) from ValidatedOrderEvent
            #            signal_id → kite_order_id  from OrderEvent
            # Combined → kite_order_id → (symbol, side) for tracker.record_order()
            _sig_to_symbol: dict[str, tuple[str, Side]] = {}

            async def _on_validated(vo: ValidatedOrderEvent) -> None:
                _sig_to_symbol[str(vo.signal_id)] = (vo.symbol, vo.side)

            async def _on_order(oe: OrderEvent) -> None:
                entry = _sig_to_symbol.get(str(oe.signal_id))
                if entry is not None:
                    symbol_, side_ = entry
                    tracker.record_order(oe.kite_order_id, symbol_, side_)

            self._bus.subscribe(validated_orders_channel, ValidatedOrderEvent, _on_validated)
            self._bus.subscribe("orders", OrderEvent, _on_order)
            self._bus.subscribe("fills", FillEvent, tracker.on_fill_event)

            # ------------------------------------------------------------------
            # 6. Build components
            # ------------------------------------------------------------------

            algo_runner = AlgoRunner(
                bus=self._bus,
                algo_name=algo.name,
                symbols=algo.instruments,
                instrument_types={s: InstrumentType.EQUITY for s in algo.instruments},
                intervals=intervals,
                strategy=make_strategy(algo.strategy_id),
                feature_engine=make_feature_engine(algo.feature_engine_id),
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
            )

            execution_engine = make_execution_engine(
                algo.execution_engine_id,
                bus=self._bus,
                broker=simulator,
                repo=repo,
                sf=sf,
                price_store=price_store,
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

            async def _on_progress(n: int) -> None:
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
                # Update price store with latest close prices from data
                # (the simulator reads from price_store for fills)

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
                cagr=cagr(eq_curve, config.initial_equity),
                calmar_ratio=calmar_ratio(eq_curve),
                total_trades=len(trades),
                final_equity=tracker.current_equity,
                session_id=session_id,
                session_type="backtest",
                started_at=started_at,
                finished_at=self._now(),
            )
            partial_report = report
            return report

        finally:
            if partial_report is not None:
                await self._persist(partial_report)


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
