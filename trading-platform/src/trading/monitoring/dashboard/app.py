from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.clock import SYSTEM_CLOCK, Clock
from trading.core.models import AlgoConfig, Candle, DecisionLog, Heartbeat, Order, Position, Signal

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def build_app(
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock = SYSTEM_CLOCK,
) -> FastAPI:
    """
    Build the monitoring dashboard FastAPI application.

    All endpoints are read-only — the dashboard never writes to the DB.
    The ``session_factory`` is the same singleton used by all other components.

    Session filtering
    -----------------
    All decision-log endpoints accept an optional ``session_id`` query param:
    - Omitted / empty → live trading view (``session_id IS NULL`` in DB)
    - Named string    → backtest / Monte Carlo session
    """
    app = FastAPI(title="Algo Trading Dashboard", docs_url=None, redoc_url=None)

    def _today_start() -> datetime:
        now = clock.now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ------------------------------------------------------------------
    # Root — serve the single-page dashboard
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        html = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(content=html)

    # ------------------------------------------------------------------
    # GET /api/sessions — list all distinct session_ids (for session selector)
    # ------------------------------------------------------------------

    @app.get("/api/sessions")
    async def get_sessions() -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(
                select(DecisionLog.session_id).distinct().order_by(DecisionLog.session_id)
            )
            rows = result.fetchall()

        sessions = [r[0] for r in rows]  # may include None (live trading)
        return JSONResponse(content=sessions)

    # ------------------------------------------------------------------
    # GET /api/positions — current open positions (JSON)
    # ------------------------------------------------------------------

    @app.get("/api/positions")
    async def get_positions() -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(
                select(Position)
                .where(Position.updated_at >= _today_start())
                .order_by(Position.symbol)
            )
            positions = result.scalars().all()

        return JSONResponse(
            content=[
                {
                    "symbol": p.symbol,
                    "instrument_type": p.instrument_type,
                    "net_qty": p.net_qty,
                    "avg_price": float(p.avg_price),
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in positions
            ]
        )

    # ------------------------------------------------------------------
    # GET /api/health — heartbeat status (JSON)
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def get_health() -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(select(Heartbeat).order_by(Heartbeat.module))
            heartbeats = result.scalars().all()

        now = clock.now()
        stale_threshold = 30

        rows = []
        for hb in heartbeats:
            last_seen = hb.last_seen
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=UTC)
            stale = (now - last_seen).total_seconds() > stale_threshold
            rows.append(
                {
                    "module": hb.module,
                    "last_seen": last_seen.isoformat(),
                    "stale": stale,
                }
            )
        return JSONResponse(content=rows)

    # ------------------------------------------------------------------
    # GET /api/signals?session_id= — last 50 signals (JSON)
    # ------------------------------------------------------------------

    @app.get("/api/signals")
    async def get_signals(session_id: str = "") -> JSONResponse:
        async with session_factory() as session:
            stmt = (
                select(DecisionLog)
                .where(
                    DecisionLog.step.in_(
                        ["SIGNAL_GENERATED", "SIGNAL_ACCEPTED", "SIGNAL_REJECTED"]
                    ),
                    DecisionLog.created_at >= _today_start(),
                    _session_filter(DecisionLog, session_id),
                )
                .order_by(DecisionLog.created_at.desc())
                .limit(50)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return JSONResponse(
            content=[
                {
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "symbol": r.symbol,
                    "algo_name": r.algo_name or "—",
                    "step": r.step,
                    "context": r.context,
                }
                for r in rows
            ]
        )

    # ------------------------------------------------------------------
    # GET /api/algos — algo config + live state (JSON)
    # ------------------------------------------------------------------

    @app.get("/api/algos")
    async def get_algos() -> JSONResponse:
        from trading.storage.stores.config import ConfigStore

        algos = await ConfigStore(session_factory).get_algo_configs_with_state()
        return JSONResponse(content=algos)

    # ------------------------------------------------------------------
    # GET /api/candles?symbol=&interval=&limit= — OHLCV bars (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/candles")
    async def get_candles_endpoint(
        symbol: str = "INFY",
        interval: str = "15min",
        limit: int = 100,
    ) -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(
                select(Candle)
                .where(
                    Candle.symbol == symbol,
                    Candle.interval == interval,
                    Candle.ts >= _today_start(),
                )
                .order_by(Candle.ts.desc())
                .limit(limit)
            )
            rows = list(reversed(result.scalars().all()))

        points = [
            {
                "ts": c.ts.isoformat(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in rows
        ]
        return JSONResponse(content=points)

    # ------------------------------------------------------------------
    # GET /api/ticks?symbol=&limit= — recent tick prices (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/ticks")
    async def get_ticks(symbol: str = "INFY", limit: int = 500) -> JSONResponse:
        async with session_factory() as session:
            from trading.core.models import TickLog

            result = await session.execute(
                select(TickLog)
                .where(
                    TickLog.symbol == symbol,
                    TickLog.received_at >= _today_start(),
                )
                .order_by(TickLog.received_at.desc())
                .limit(limit)
            )
            ticks = list(reversed(result.scalars().all()))

        points = [{"ts": t.received_at.isoformat(), "price": float(t.last_price)} for t in ticks]
        return JSONResponse(content=points)

    # ------------------------------------------------------------------
    # GET /api/pnl?session_id= — cumulative P&L time series (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/pnl")
    async def get_pnl(session_id: str = "") -> JSONResponse:
        from trading.reports.fetch import fetch_nifty_benchmark
        from trading.reports.pnl import DEFAULT_COSTS

        today = _today_start()

        async with session_factory() as session:
            result = await session.execute(
                select(Order, Signal)
                .join(Signal, Order.signal_id == Signal.id)
                .where(
                    Order.status == "FILLED",
                    Order.created_at >= today,
                )
                .order_by(Order.created_at)
            )
            rows = result.all()
            nifty = await fetch_nifty_benchmark(session, today, clock.now())

        cum_gross = 0.0
        cum_net = 0.0
        points: list[dict[str, object]] = []
        for order, signal in rows:
            sign = 1.0 if signal.side == "SELL" else -1.0
            notional = float(order.avg_price) * order.qty
            cost = DEFAULT_COSTS.cost_for_fill(signal.side, order.qty, float(order.avg_price))
            cum_gross += sign * notional
            cum_net += sign * notional - cost
            ts = order.created_at
            points.append(
                {
                    "ts": ts.isoformat() if ts else "",
                    "cumulative_gross": round(cum_gross, 2),
                    "cumulative_net": round(cum_net, 2),
                    "side": signal.side,
                    "qty": order.qty,
                    "price": float(order.avg_price),
                    "cost": round(cost, 2),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
                }
            )

        total_costs = round(cum_gross - cum_net, 2)
        summary: dict[str, object] = {
            "gross": round(cum_gross, 2),
            "costs": total_costs,
            "net": round(cum_net, 2),
            "nifty_pct": round(nifty["pct_return"], 2) if nifty else None,
            "nifty_open": round(nifty["open"], 2) if nifty else None,
            "nifty_close": round(nifty["close"], 2) if nifty else None,
        }

        return JSONResponse(content={"points": points, "summary": summary})

    # ------------------------------------------------------------------
    # GET /api/charts?session_id=&limit= — indicator chart series (JSON)
    # ------------------------------------------------------------------

    @app.get("/api/charts")
    async def get_charts(session_id: str = "", limit: int = 500) -> JSONResponse:
        from trading.storage.stores.chart import ChartStore

        chart_store = ChartStore(session_factory)
        sid: str | None = session_id if session_id else None
        since = _today_start()

        async with session_factory() as session:
            # Collect all algo names
            result = await session.execute(select(AlgoConfig.name))
            algo_names = [r[0] for r in result.fetchall()]

        # For each algo, get chart names then fetch each chart's series
        combined: dict[str, dict[str, list[dict]]] = {}
        for algo_name in algo_names:
            chart_names = await chart_store.get_chart_names(algo_name, since, sid)
            for chart_name in chart_names:
                series = await chart_store.get_indicator_series(
                    algo_name, chart_name, since, sid, limit
                )
                # Merge series from multiple algos into the same chart bucket
                if chart_name not in combined:
                    combined[chart_name] = {}
                combined[chart_name].update(series)

        return JSONResponse(content=combined)

    # ------------------------------------------------------------------
    # GET /api/decisions/stream?session_id= — SSE live decision feed
    # ------------------------------------------------------------------

    @app.get("/api/decisions/stream")
    async def decisions_stream(request: Request, session_id: str = "") -> StreamingResponse:
        async def _event_generator() -> AsyncIterator[str]:
            yield ": connected\n\n"  # triggers EventSource.onopen immediately
            last_id = 0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    async with session_factory() as session:
                        stmt = (
                            select(DecisionLog)
                            .where(
                                DecisionLog.id > last_id,
                                DecisionLog.created_at >= _today_start(),
                                _session_filter(DecisionLog, session_id),
                            )
                            .order_by(DecisionLog.id)
                            .limit(20)
                        )
                        result = await session.execute(stmt)
                        new_rows = result.scalars().all()

                    for row in new_rows:
                        last_id = row.id
                        payload = json.dumps(
                            {
                                "id": row.id,
                                "tick_log_id": row.tick_log_id,
                                "step": row.step,
                                "symbol": row.symbol,
                                "algo": row.algo_name,
                                "ts": row.created_at.isoformat() if row.created_at else None,
                                "context": json.loads(row.context) if row.context else {},
                            }
                        )
                        yield f"data: {payload}\n\n"
                except Exception as exc:
                    logger.debug("SSE generator error: %s", exc)
                await asyncio.sleep(2)

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _session_filter(model: type[DecisionLog], session_id: str) -> object:
    if session_id:
        return model.session_id == session_id
    return model.session_id.is_(None)
