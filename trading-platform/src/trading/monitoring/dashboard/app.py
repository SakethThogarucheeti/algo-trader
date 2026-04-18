from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.core.models import DecisionLog, Heartbeat, Order, Position

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


def build_app(session_factory: async_sessionmaker[AsyncSession]) -> FastAPI:
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
                text("SELECT DISTINCT session_id FROM decision_logs ORDER BY session_id")
            )
            rows = result.fetchall()

        sessions = [r[0] for r in rows]  # may include None (live trading)
        return JSONResponse(content=sessions)

    # ------------------------------------------------------------------
    # GET /api/positions — current open positions (htmx fragment)
    # ------------------------------------------------------------------

    @app.get("/api/positions", response_class=HTMLResponse)
    async def get_positions() -> HTMLResponse:
        async with session_factory() as session:
            result = await session.execute(select(Position).order_by(Position.symbol))
            positions = result.scalars().all()

        if not positions:
            return HTMLResponse(_empty_table("No open positions"))

        rows_html = "".join(
            f"<tr>"
            f"<td>{p.symbol}</td>"
            f"<td>{p.instrument_type}</td>"
            f"<td class='{'pos' if p.net_qty > 0 else 'neg'}'>{p.net_qty:+d}</td>"
            f"<td>{float(p.avg_price):.2f}</td>"
            f"<td>{p.updated_at.strftime('%H:%M:%S') if p.updated_at else '—'}</td>"
            f"</tr>"
            for p in positions
        )
        return HTMLResponse(
            f"<table class='data-table'>"
            "<thead><tr>"
            "<th>Symbol</th><th>Type</th><th>Qty</th><th>Avg Price</th><th>Updated</th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
        )

    # ------------------------------------------------------------------
    # GET /api/health — heartbeat status (htmx fragment)
    # ------------------------------------------------------------------

    @app.get("/api/health", response_class=HTMLResponse)
    async def get_health() -> HTMLResponse:
        async with session_factory() as session:
            result = await session.execute(select(Heartbeat).order_by(Heartbeat.module))
            heartbeats = result.scalars().all()

        if not heartbeats:
            return HTMLResponse(_empty_table("No heartbeat data yet"))

        now = datetime.now(UTC)
        stale_threshold = 30  # seconds — matches heartbeat_timeout_secs default

        rows_html = "".join(_heartbeat_row(hb, now, stale_threshold) for hb in heartbeats)
        return HTMLResponse(
            f"<table class='data-table'>"
            f"<thead><tr><th>Module</th><th>Last Seen</th><th>Status</th></tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
        )

    # ------------------------------------------------------------------
    # GET /api/signals?session_id= — last 50 signals (htmx fragment)
    # ------------------------------------------------------------------

    @app.get("/api/signals", response_class=HTMLResponse)
    async def get_signals(session_id: str = "") -> HTMLResponse:
        async with session_factory() as session:
            stmt = (
                select(DecisionLog)
                .where(
                    DecisionLog.step.in_(
                        ["SIGNAL_GENERATED", "SIGNAL_ACCEPTED", "SIGNAL_REJECTED"]
                    ),
                    _session_filter(DecisionLog, session_id),
                )
                .order_by(DecisionLog.created_at.desc())
                .limit(50)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        if not rows:
            return HTMLResponse(_empty_table("No signals yet"))

        rows_html = "".join(
            f"<tr>"
            f"<td>{r.created_at.strftime('%H:%M:%S') if r.created_at else '—'}</td>"
            f"<td>{r.symbol}</td>"
            f"<td>{r.algo_name or '—'}</td>"
            f"<td class='{_step_class(r.step)}'>{r.step}</td>"
            f"<td>{_context_summary(r.context)}</td>"
            f"</tr>"
            for r in rows
        )
        return HTMLResponse(
            f"<table class='data-table'>"
            f"<thead><tr><th>Time</th><th>Symbol</th><th>Algo</th><th>Step</th><th>Context</th></tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
        )

    # ------------------------------------------------------------------
    # GET /api/pnl?session_id= — cumulative P&L time series (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/pnl")
    async def get_pnl(session_id: str = "") -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(
                select(Order).where(Order.status == "FILLED").order_by(Order.created_at)
            )
            orders = result.scalars().all()

        cumulative = 0.0
        points: list[dict[str, object]] = []
        for order in orders:
            # Approximation: each filled order contributes qty * avg_price to cash flow.
            # SELL = money in (+), BUY = money out (−). We track absolute P&L movement.
            cumulative += float(order.avg_price) * order.qty
            ts = order.created_at
            points.append(
                {
                    "ts": ts.isoformat() if ts else "",
                    "cumulative_pnl": round(cumulative, 2),
                }
            )

        return JSONResponse(content=points)

    # ------------------------------------------------------------------
    # GET /api/decisions/stream?session_id= — SSE live decision feed
    # ------------------------------------------------------------------

    @app.get("/api/decisions/stream")
    async def decisions_stream(request: Request, session_id: str = "") -> StreamingResponse:
        async def _event_generator() -> AsyncIterator[str]:
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
    """Build a SQLAlchemy WHERE clause for session_id filtering."""
    if session_id:
        return model.session_id == session_id
    return model.session_id.is_(None)


def _empty_table(message: str) -> str:
    return f"<p class='empty-state'>{message}</p>"


def _heartbeat_row(hb: Heartbeat, now: datetime, stale_threshold: int) -> str:
    last_seen = hb.last_seen
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    age_secs = (now - last_seen).total_seconds()
    is_stale = age_secs > stale_threshold
    status_cls = "neg" if is_stale else "pos"
    status_txt = "STALE" if is_stale else "OK"
    return (
        f"<tr>"
        f"<td>{hb.module}</td>"
        f"<td>{last_seen.strftime('%H:%M:%S')}</td>"
        f"<td class='{status_cls}'>{status_txt}</td>"
        f"</tr>"
    )


def _step_class(step: str) -> str:
    return {
        "SIGNAL_ACCEPTED": "pos",
        "SIGNAL_REJECTED": "neg",
        "SIGNAL_GENERATED": "neutral",
    }.get(step, "")


def _context_summary(context_json: str) -> str:
    try:
        ctx = json.loads(context_json)
        if "reason" in ctx:
            return ctx["reason"]
        if "qty" in ctx:
            return f"qty={ctx['qty']}"
        return ", ".join(f"{k}={v}" for k, v in list(ctx.items())[:3])
    except Exception:
        return context_json[:60] if context_json else "—"
