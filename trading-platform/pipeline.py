"""
Trading pipeline — single file that wires the entire tick-to-execution flow.

Read this file top-to-bottom to understand the full system:
  1. Configure each stage (what instruments, what strategy, what risk limits)
  2. Construct each registry (resolves concrete implementations from config IDs)
  3. Define on_tick() — the flat pipeline called once per incoming market tick

To change strategy: edit instrument_strategy_map.
To change risk limits: edit RiskConfig.
To switch paper/live: change exec_id in TickConfig.
"""

from __future__ import annotations

import logging

from trading.registry.algo import AlgoConfig, AlgoRegistry
from trading.registry.candle import CandleConfig, CandleRegistry
from trading.registry.exec import ExecConfig, ExecRegistry
from trading.registry.risk import RiskConfig, RiskRegistry
from trading.registry.tick import TickConfig, TickRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Infrastructure (injected at startup — replace with your real instances)
# ---------------------------------------------------------------------------
# These are provided by the DI container in production.
# For standalone use, construct them directly:
#
#   from trading.core.database import build_engine, build_session_factory
#   engine = build_engine(settings.postgres_url)
#   sf = build_session_factory(engine)
#   repo = Repository()
#   broker = ZerodhaBroker(kite_client)
#   stream = ZerodhaStream(kite_client)
#   price_store = PriceStore()  # only needed for paper trading
#
# ---------------------------------------------------------------------------


def build_pipeline(
    *,
    stream,  # BrokerStream
    broker,  # Broker
    sf,  # async_sessionmaker[AsyncSession]
    repo,  # AbstractRepository
    price_store=None,  # AbstractPriceStore | None — set for paper trading
):
    """
    Construct all pipeline registries and return the on_tick coroutine.

    Returns (tick_reg, candle_reg, algo_reg, risk_reg, exec_reg, on_tick)
    so callers can pass tick_reg to KiteIngestor and risk_reg.circuit to
    any external circuit-breaker consumers.
    """

    # ------------------------------------------------------------------
    # Stage 1 — Tick ingestion
    # ------------------------------------------------------------------
    tick_config = TickConfig(
        instruments=[],  # populated from DB at startup via DI; override here for standalone
        exec_id="paper",  # "paper" | "direct"
    )
    tick_reg = TickRegistry(
        config=tick_config,
        stream=stream,
        session_factory=sf,
        repo=repo,
    )

    # ------------------------------------------------------------------
    # Stage 2 — Candle aggregation
    # ------------------------------------------------------------------
    candle_config = CandleConfig(
        instruments=[],  # same list as tick_config.instruments
        intervals=["1min", "5min"],
        warmup_count=200,
    )
    candle_reg = CandleRegistry(
        config=candle_config,
        broker=broker,
        session_factory=sf,
        repo=repo,
    )

    # ------------------------------------------------------------------
    # Stage 3 — Strategy / algo
    #
    # instrument_strategy_map decides which strategy runs for each symbol.
    # Add an entry per instrument — resolved at runtime from the ID string.
    # ------------------------------------------------------------------
    algo_config = AlgoConfig(
        instrument_strategy_map={
            "INFY": "ema_crossover",
            "TCS": "ema_crossover",
        },
        instrument_feature_map={
            "INFY": "technical",
            "TCS": "technical",
        },
        instrument_types={
            "INFY": "EQUITY",
            "TCS": "EQUITY",
        },
        equity=10_000.0,
        warmup_candles=200,
        algo_name="default",
    )
    algo_reg = AlgoRegistry(
        config=algo_config,
        session_factory=sf,
        repo=repo,
    )

    # ------------------------------------------------------------------
    # Stage 4 — Risk evaluation
    #
    # circuit is owned by tick_reg — same object, no copy.
    # ------------------------------------------------------------------
    risk_config = RiskConfig(
        equity=10_000.0,
        max_daily_loss_pct=2.0,
        risk_per_trade_pct=1.0,
        rc_id="default",
        paper_trading=(tick_config.exec_id == "paper"),
        intraday_cutoff_hour=15,
        intraday_cutoff_minute=30,
    )
    risk_reg = RiskRegistry(
        config=risk_config,
        circuit=tick_reg.circuit,  # same CircuitBreaker instance as tick_reg
        session_factory=sf,
        repo=repo,
    )

    # ------------------------------------------------------------------
    # Stage 5 — Execution
    # ------------------------------------------------------------------
    exec_config = ExecConfig(exec_id=tick_config.exec_id)
    exec_reg = ExecRegistry(
        config=exec_config,
        broker=broker,
        session_factory=sf,
        repo=repo,
        price_store=price_store,
    )

    # ------------------------------------------------------------------
    # Pipeline — called once per incoming WebSocket tick
    # ------------------------------------------------------------------
    async def on_tick(raw: dict) -> None:
        tick = await tick_reg.handle(raw)
        if tick is None:
            return

        candle = await candle_reg.handle(tick)
        if candle is None:
            return

        signals = await algo_reg.handle(candle)
        for signal in signals:
            order = await risk_reg.handle(signal)
            if order is None:
                continue
            await exec_reg.handle(order)

    return tick_reg, candle_reg, algo_reg, risk_reg, exec_reg, on_tick
