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

from trading.core.models import DecisionLog, Heartbeat, Order, Position, Signal

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
    # GET /api/algos — algo config + live state (htmx fragment)
    # ------------------------------------------------------------------

    @app.get("/api/algos", response_class=HTMLResponse)
    async def get_algos() -> HTMLResponse:
        from trading.storage.repository import Repository
        repo = Repository()
        async with session_factory() as session:
            algos = await repo.get_algo_configs_with_state(session)

        if not algos:
            return HTMLResponse(_empty_table("No algo configs found — bot not started yet"))

        cards = "".join(_algo_card(a) for a in algos)
        return HTMLResponse(cards)

    # ------------------------------------------------------------------
    # GET /api/ticks?symbol=&limit= — recent tick prices (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/ticks")
    async def get_ticks(symbol: str = "INFY", limit: int = 500) -> JSONResponse:
        async with session_factory() as session:
            from trading.core.models import TickLog
            result = await session.execute(
                select(TickLog)
                .where(TickLog.symbol == symbol)
                .order_by(TickLog.received_at.desc())
                .limit(limit)
            )
            ticks = list(reversed(result.scalars().all()))

        points = [
            {"ts": t.received_at.isoformat(), "price": float(t.last_price)}
            for t in ticks
        ]
        return JSONResponse(content=points)

    # ------------------------------------------------------------------
    # GET /api/pnl?session_id= — cumulative P&L time series (Chart.js JSON)
    # ------------------------------------------------------------------

    @app.get("/api/pnl")
    async def get_pnl(session_id: str = "") -> JSONResponse:
        async with session_factory() as session:
            result = await session.execute(
                select(Order, Signal)
                .join(Signal, Order.signal_id == Signal.id)
                .where(Order.status == "FILLED")
                .order_by(Order.created_at)
            )
            rows = result.all()

        cumulative = 0.0
        points: list[dict[str, object]] = []
        for order, signal in rows:
            cumulative += float(order.avg_price) * order.qty
            ts = order.created_at
            points.append(
                {
                    "ts": ts.isoformat() if ts else "",
                    "cumulative_pnl": round(cumulative, 2),
                    "side": signal.side,
                    "qty": order.qty,
                    "price": float(order.avg_price),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
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


def _algo_card(algo: dict[str, object]) -> str:
    state: dict[str, object] = algo.get("state", {})  # type: ignore[assignment]
    bars_seen = state.get("bars_seen", 0)
    warmup_candles = state.get("warmup_candles") or algo.get("warmup_candles", 0)
    warmup_complete = state.get("warmup_complete", False)
    bars_remaining = state.get("bars_remaining", warmup_candles)
    last_signal_at = state.get("last_signal_at") or "—"
    params: dict[str, object] = algo.get("params", {})  # type: ignore[assignment]

    pct = min(100, int(bars_seen / warmup_candles * 100)) if warmup_candles else 100
    bar_colour = "var(--pos)" if warmup_complete else "var(--neutral)"
    status_label = (
        "<span class='pos'>LIVE</span>"
        if warmup_complete
        else f"<span class='neutral'>{bars_remaining} bars until live</span>"
    )

    # Strategy params rows
    param_rows = "".join(
        f"<tr><td style='color:var(--muted)'>{k}</td><td>{v}</td></tr>"
        for k, v in params.items()
    ) if params else ""

    # Live state rows — skip internal bookkeeping keys shown elsewhere
    _skip = {"bars_seen", "warmup_candles", "warmup_complete", "bars_remaining", "last_signal_at"}
    state_rows = "".join(
        f"<tr><td style='color:var(--muted)'>{k}</td><td>{v if v is not None else '—'}</td></tr>"
        for k, v in state.items()
        if k not in _skip
    )

    return f"""
<div style="margin-bottom:1rem;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
    <span style="font-weight:600">{algo['name']}</span>
    <span style="font-size:11px;color:var(--muted)">{algo['strategy_id']}</span>
    {status_label}
  </div>
  <div style="background:var(--border);border-radius:4px;height:6px;margin-bottom:0.6rem;">
    <div style="width:{pct}%;height:6px;border-radius:4px;background:{bar_colour};transition:width 0.5s;"></div>
  </div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:0.5rem;">
    {bars_seen} / {warmup_candles} warm-up bars &nbsp;·&nbsp; last signal: {last_signal_at}
  </div>
  {"<table class='data-table' style='margin-bottom:0.4rem'>" + param_rows + "</table>" if param_rows else ""}
  {"<table class='data-table'>" + state_rows + "</table>" if state_rows else ""}
</div>"""
