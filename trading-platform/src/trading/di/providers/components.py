from __future__ import annotations

import logging

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.broker.base.broker_stream import BrokerStream
from trading.broker.paper_broker import AbstractPriceStore
from trading.config.settings import AlgoSettings, Settings
from trading.di.providers.strategy import make_strategy
from trading.engine.algo_runner import AlgoRunner
from trading.engine.candle_aggregator import CandleAggregator
from trading.engine.component import Component
from trading.engine.heartbeat import HeartbeatMonitor
from trading.engine.kite_ingestor import KiteIngestor, OnTickCallback
from trading.engine.runtime import AbstractRuntime, Runtime
from trading.engine.scheduler import Scheduler
from trading.execution.executor import OrderExecutor
from trading.indicators.context import IndicatorContext
from trading.indicators.polars_store import PolarsStore
from trading.registry.algo import AlgoConfig, AlgoRegistry, _AlgoInstance
from trading.registry.candle import CandleConfig, CandleRegistry
from trading.registry.exec import ExecConfig, ExecRegistry
from trading.registry.risk import RiskConfig, RiskRegistry
from trading.registry.tick import TickConfig, TickRegistry
from trading.risk.base import RiskController
from trading.storage.base import AbstractRepository

logger = logging.getLogger(__name__)


class ComponentProvider(Provider):
    scope = Scope.APP

    @provide
    async def tick_registry(
        self,
        stream: BrokerStream,
        repo: AbstractRepository,
        sf: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> TickRegistry:
        from sqlalchemy import select

        from trading.core.models import Instrument

        async with sf() as session:
            instruments = list((await session.execute(select(Instrument))).scalars().all())

        exec_id = "paper" if settings.paper_trading else "direct"
        config = TickConfig(instruments=instruments, exec_id=exec_id)
        return TickRegistry(
            config=config,
            stream=stream,
            session_factory=sf,
            repo=repo,
            circuit_timeout_secs=settings.circuit_timeout_secs,
        )

    @provide
    async def candle_registry(
        self,
        broker: Broker,
        repo: AbstractRepository,
        sf: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> CandleRegistry:
        from sqlalchemy import select

        from trading.core.models import Instrument

        async with sf() as session:
            instruments = list((await session.execute(select(Instrument))).scalars().all())

        config = CandleConfig(
            instruments=instruments,
            intervals=settings.candle_intervals,
            warmup_count=settings.warmup_candles,
        )
        return CandleRegistry(config=config, broker=broker, session_factory=sf, repo=repo)

    @provide
    def heartbeat_monitor(
        self,
        repo: AbstractRepository,
        sf: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> HeartbeatMonitor:
        from trading.monitoring.telegram import TelegramAlerter

        alerter = TelegramAlerter(settings)

        async def _alert(module: str) -> None:
            await alerter.send_alert(
                f"Heartbeat missed: {module} is unresponsive",
                event_type=f"heartbeat:{module}",
            )

        return HeartbeatMonitor(
            repo, sf,
            component_names=["heartbeat_monitor"],
            beat_interval_secs=settings.heartbeat_interval_secs,
            timeout_secs=settings.heartbeat_timeout_secs,
            alerter=_alert,
        )

    @provide
    async def runtime(
        self,
        tick_registry: TickRegistry,
        candle_registry: CandleRegistry,
        heartbeat_monitor: HeartbeatMonitor,
        stream: BrokerStream,
        broker: Broker,
        repo: AbstractRepository,
        price_store: AbstractPriceStore,
        settings: Settings,
        sf: async_sessionmaker[AsyncSession],
    ) -> AbstractRuntime:
        from sqlalchemy import select

        from trading.core.models import Instrument
        from trading.core.schemas import InstrumentType, TickEvent

        exec_id = "paper" if settings.paper_trading else "direct"
        algo_configs = settings.algos
        if not algo_configs:
            async with sf() as session:
                rows = list((await session.execute(select(Instrument))).scalars().all())
            all_symbols = [r.symbol for r in rows]
            algo_configs = [
                AlgoSettings(
                    name="default",
                    instruments=all_symbols,
                    broker_name="paper" if settings.paper_trading else "zerodha",
                    execution_engine_id=exec_id,
                    equity=settings.default_equity,
                )
            ]
        elif settings.paper_trading:
            algo_configs = [
                a.model_copy(update={"execution_engine_id": exec_id}) for a in algo_configs
            ]

        async with sf() as session:
            rows = list((await session.execute(select(Instrument))).scalars().all())
        instrument_type_map = {r.symbol: r.instrument_type for r in rows}

        paper_price_store = price_store if settings.paper_trading else None

        # Shared in-memory store + IndicatorContext (one per algo, wired below)
        polars_store = PolarsStore()

        algo_runners: list[Component] = []
        risk_controllers: list[Component] = []
        order_executors: list[Component] = []

        # Build ingestor and candle aggregator up front so we can wire callbacks into them.
        ingestor = KiteIngestor(
            stream=stream,
            tick_registry=tick_registry,
            price_store=paper_price_store,
            connect_timeout_secs=settings.ws_connect_timeout_secs,
        )
        candle_aggregator = CandleAggregator(candle_registry)

        for algo in algo_configs:
            intervals = algo.candle_intervals or settings.candle_intervals

            algo_instances: dict[str, _AlgoInstance] = {
                s: _AlgoInstance(
                    strategy=make_strategy(algo.strategy_id),
                    instrument_type=InstrumentType(
                        instrument_type_map.get(s, InstrumentType.EQUITY.value)
                    ),
                )
                for s in algo.instruments
            }
            indicator_ctx = IndicatorContext(polars_store)
            algo_reg = AlgoRegistry(
                config=AlgoConfig(
                    instrument_strategy_map={s: algo.strategy_id for s in algo.instruments},
                    instrument_types={
                        s: instrument_type_map.get(s, InstrumentType.EQUITY.value)
                        for s in algo.instruments
                    },
                    equity=algo.equity,
                    warmup_candles=settings.warmup_candles,
                    algo_name=algo.name,
                ),
                session_factory=sf,
                repo=repo,
                algos=algo_instances,
                store=polars_store,
            )
            algo_reg.set_indicator_context(indicator_ctx)

            risk_reg = RiskRegistry(
                config=RiskConfig(
                    equity=algo.equity,
                    max_daily_loss_pct=settings.max_daily_loss_pct,
                    risk_per_trade_pct=settings.risk_per_trade_pct,
                    rc_id=algo.risk_controller_id,
                    paper_trading=settings.paper_trading,
                    intraday_cutoff_hour=settings.intraday_cutoff_hour,
                    intraday_cutoff_minute=settings.intraday_cutoff_minute,
                ),
                circuit=tick_registry.circuit,
                session_factory=sf,
                repo=repo,
            )

            exec_reg = ExecRegistry(
                config=ExecConfig(exec_id=algo.execution_engine_id),
                broker=broker,
                session_factory=sf,
                repo=repo,
                price_store=paper_price_store,
            )

            # Seed algo config into DB on first run
            strategy = make_strategy(algo.strategy_id)
            async with sf() as session:
                async with session.begin():
                    await repo.seed_algo_config(
                        session,
                        name=algo.name,
                        strategy_id=algo.strategy_id,
                        warmup_candles=settings.warmup_candles,
                        candle_intervals=intervals,
                        equity=algo.equity,
                        params=strategy.get_params(),
                    )

            # Wire warmup replay: CandleAggregator feeds historical candles into algo_reg
            candle_aggregator.add_algo_registry(algo_reg)

            # Wire live pipeline: tick → candle → algo → risk → exec
            def _make_on_tick(
                ar: AlgoRegistry, rr: RiskRegistry, er: ExecRegistry
            ) -> OnTickCallback:
                async def _on_tick(tick: TickEvent) -> None:
                    candle = await candle_registry.handle(tick)
                    if candle is None:
                        return
                    signals = await ar.handle(candle)
                    for signal in signals:
                        order = await rr.handle(signal)
                        if order is None:
                            continue
                        await er.handle(order)
                return _on_tick

            ingestor.add_on_tick(_make_on_tick(algo_reg, risk_reg, exec_reg))

            algo_runners.append(AlgoRunner(algo_reg))
            risk_controllers.append(RiskController(risk_reg))
            order_executors.append(OrderExecutor(exec_reg))

            logger.info(
                "ComponentProvider: algo=%r strategy=%r risk=%r exec=%r instruments=%d equity=%.0f",
                algo.name, algo.strategy_id, algo.risk_controller_id,
                algo.execution_engine_id, len(algo.instruments), algo.equity,
            )

        dashboard_components: list[Component] = []
        if settings.dashboard_enabled:
            from trading.monitoring.dashboard.component import DashboardServer
            dashboard_components.append(DashboardServer(
                session_factory=sf,
                host=settings.dashboard_host,
                port=settings.dashboard_port,
            ))

        return Runtime([
            ingestor,
            candle_aggregator,
            *algo_runners,
            *risk_controllers,
            *order_executors,
            heartbeat_monitor,
            *dashboard_components,
        ])

    @provide
    def scheduler(self, settings: Settings, runtime: AbstractRuntime) -> Scheduler:
        return Scheduler(
            settings,
            on_market_open=runtime.start,
            on_market_close=runtime.stop,
        )
