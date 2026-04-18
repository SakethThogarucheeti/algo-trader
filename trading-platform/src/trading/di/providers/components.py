from __future__ import annotations

import logging

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.broker.base.broker import Broker
from trading.broker.base.broker_stream import BrokerStream
from trading.broker.paper_broker import PriceStore
from trading.config.settings import AlgoSettings, Settings
from trading.core.messaging import MessageBus
from trading.data.candles import CandleAggregator, _SymbolConfig
from trading.data.realtime import KiteIngestor
from trading.di.providers.execution import make_execution_engine
from trading.di.providers.features import make_feature_engine
from trading.di.providers.risk import make_risk_controller
from trading.di.providers.strategy import make_strategy
from trading.engine.component import Component
from trading.engine.heartbeat import HeartbeatMonitor
from trading.engine.runtime import Runtime
from trading.engine.scheduler import Scheduler
from trading.storage.repository import Repository

logger = logging.getLogger(__name__)


class ComponentProvider(Provider):
    """
    Assembles all trading components for all configured algos.

    For each algo in ``settings.algos``, the provider creates:
    - An ``AlgoRunner`` (strategy + feature engine, subscribes to candles)
    - A ``RiskController`` (scoped to this algo's signals channel)
    - An ``OrderExecutor`` (scoped to this algo's validated_orders channel)

    Infra singletons (broker, ingestor, candle aggregator, heartbeat) are
    shared across all algos.

    Backward compatibility: if ``settings.algos`` is empty, a single default
    algo is assembled from all instruments in the database.
    """

    scope = Scope.APP

    @provide
    async def ingestor(
        self,
        stream: BrokerStream,
        bus: MessageBus,
        price_store: PriceStore,
        repo: Repository,
        settings: Settings,
        sf: async_sessionmaker[AsyncSession],
    ) -> KiteIngestor:
        from sqlalchemy import select

        from trading.core.models import Instrument

        async with sf() as session:
            rows = (await session.execute(select(Instrument))).scalars().all()

        instruments: list[Instrument] = list(rows)
        logger.info("ComponentProvider: loaded %d instruments from DB", len(instruments))
        return KiteIngestor(
            stream=stream,
            bus=bus,
            instruments=instruments,
            session_factory=sf,
            repo=repo,
            price_store=price_store if settings.paper_trading else None,
        )

    @provide
    async def candle_aggregator(
        self,
        bus: MessageBus,
        broker: Broker,
        repo: Repository,
        settings: Settings,
        sf: async_sessionmaker[AsyncSession],
    ) -> CandleAggregator:
        from sqlalchemy import select

        from trading.core.models import Instrument
        from trading.core.schemas import InstrumentType

        async with sf() as session:
            rows = (await session.execute(select(Instrument))).scalars().all()

        symbols: list[_SymbolConfig] = [
            _SymbolConfig(
                symbol=r.symbol,
                instrument_token=r.token,
                instrument_type=InstrumentType(r.instrument_type),
            )
            for r in rows
        ]
        return CandleAggregator(
            bus=bus,
            broker=broker,
            symbols=symbols,
            intervals=settings.candle_intervals,
            session_factory=sf,
            repo=repo,
            warmup_count=settings.warmup_candles,
        )

    @provide
    def heartbeat_monitor(
        self,
        repo: Repository,
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

        component_names = ["heartbeat_monitor"]
        return HeartbeatMonitor(
            repo,
            sf,
            component_names,
            beat_interval_secs=settings.heartbeat_interval_secs,
            timeout_secs=settings.heartbeat_timeout_secs,
            alerter=_alert,
        )

    @provide
    async def runtime(
        self,
        ingestor: KiteIngestor,
        candle_aggregator: CandleAggregator,
        heartbeat_monitor: HeartbeatMonitor,
        bus: MessageBus,
        broker: Broker,
        repo: Repository,
        price_store: PriceStore,
        settings: Settings,
        sf: async_sessionmaker[AsyncSession],
    ) -> Runtime:
        from sqlalchemy import select

        from trading.core.models import Instrument
        from trading.core.schemas import InstrumentType
        from trading.engine.algo_runner import AlgoRunner
        from trading.execution.executor import OrderExecutor

        # ------------------------------------------------------------------
        # Build algo list — fall back to a single default algo if none configured
        # ------------------------------------------------------------------
        algo_configs = settings.algos
        if not algo_configs:
            async with sf() as session:
                rows = (await session.execute(select(Instrument))).scalars().all()
            all_symbols = [r.symbol for r in rows]
            algo_configs = [
                AlgoSettings(
                    name="default",
                    instruments=all_symbols,
                    broker_name="paper" if settings.paper_trading else "zerodha",
                    equity=settings.default_equity,
                )
            ]
            logger.info(
                "ComponentProvider: no algos configured — using single default algo "
                "with %d instruments",
                len(all_symbols),
            )

        # Load instrument metadata (needed to map symbol → InstrumentType)
        async with sf() as session:
            rows = (await session.execute(select(Instrument))).scalars().all()
        instrument_type_map: dict[str, InstrumentType] = {
            r.symbol: InstrumentType(r.instrument_type) for r in rows
        }

        # ------------------------------------------------------------------
        # Assemble per-algo components
        # ------------------------------------------------------------------
        algo_runners: list[Component] = []
        risk_controllers: list[Component] = []
        order_executors: list[Component] = []

        paper_price_store = price_store if settings.paper_trading else None

        for algo in algo_configs:
            intervals = algo.candle_intervals or settings.candle_intervals
            algo_symbol_types = {
                s: instrument_type_map.get(s, InstrumentType.EQUITY) for s in algo.instruments
            }

            signals_channel = f"signals:{algo.name}"
            validated_orders_channel = f"validated_orders:{algo.name}"

            algo_runners.append(
                AlgoRunner(
                    bus=bus,
                    algo_name=algo.name,
                    symbols=algo.instruments,
                    instrument_types=algo_symbol_types,
                    intervals=intervals,
                    strategy=make_strategy(algo.strategy_id),
                    feature_engine=make_feature_engine(algo.feature_engine_id),
                    session_factory=sf,
                    repo=repo,
                )
            )

            risk_controllers.append(
                make_risk_controller(
                    algo.risk_controller_id,
                    bus=bus,
                    repo=repo,
                    sf=sf,
                    settings=settings,
                    equity=algo.equity,
                    signals_channel=signals_channel,
                    validated_orders_channel=validated_orders_channel,
                )
            )

            order_executors.append(
                OrderExecutor(
                    bus=bus,
                    execution_engine=make_execution_engine(
                        algo.execution_engine_id,
                        bus=bus,
                        broker=broker,
                        repo=repo,
                        sf=sf,
                        price_store=paper_price_store,
                    ),
                    channel=validated_orders_channel,
                )
            )

            logger.info(
                "ComponentProvider: algo=%r strategy=%r risk=%r feature=%r execution=%r "
                "instruments=%d equity=%.0f",
                algo.name,
                algo.strategy_id,
                algo.risk_controller_id,
                algo.feature_engine_id,
                algo.execution_engine_id,
                len(algo.instruments),
                algo.equity,
            )

        # ------------------------------------------------------------------
        # Assemble dashboard (optional)
        # ------------------------------------------------------------------
        dashboard_components: list[Component] = []
        if settings.dashboard_enabled:
            from trading.monitoring.dashboard.component import DashboardServer

            dashboard_components.append(
                DashboardServer(
                    session_factory=sf,
                    host=settings.dashboard_host,
                    port=settings.dashboard_port,
                )
            )

        # ------------------------------------------------------------------
        # Runtime component order:
        # ingestor → candle_aggregator → algo_runners → risk_controllers
        # → order_executors → heartbeat_monitor → dashboard
        # ------------------------------------------------------------------
        return Runtime(
            [
                ingestor,
                candle_aggregator,
                *algo_runners,
                *risk_controllers,
                *order_executors,
                heartbeat_monitor,
                *dashboard_components,
            ]
        )

    @provide
    def scheduler(self, settings: Settings, runtime: Runtime) -> Scheduler:
        return Scheduler(
            settings,
            on_market_open=runtime.start,
            on_market_close=runtime.stop,
        )
