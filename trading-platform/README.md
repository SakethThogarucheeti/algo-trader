# algo-trader

An event-driven intraday trading platform for Indian equity markets, built on Zerodha/Kite.

**Architecture:** Redis pub/sub messaging · PostgreSQL persistence · APScheduler market-hours automation · Dishka DI · async-first (anyio)

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | 3.10.x recommended (see `.python-version`) |
| [uv](https://docs.astral.sh/uv/) | latest | dependency manager and runner |
| Docker + Docker Compose | v2+ | for Postgres and Redis |

---

## Setup

### 1. Clone and install dependencies

```bash
cd trading-platform
uv sync
```

### 2. Configure environment

Copy the example below into `trading-platform/.env` and fill in your values:

```dotenv
# Zerodha credentials — from https://developers.kite.trade/apps
ZERODHA_API_KEY=your_api_key
ZERODHA_API_SECRET=your_api_secret
ZERODHA_ACCESS_TOKEN=          # leave empty; populated by the login script each day

# Infrastructure (match docker-compose defaults)
POSTGRES_URL=postgresql+asyncpg://trading:trading@localhost/trading
REDIS_URL=redis://localhost:6379

# Risk controls (optional — safe defaults shown)
MAX_DAILY_LOSS_PCT=2.0         # halt trading if daily PnL drops this % of equity
RISK_PER_TRADE_PCT=1.0         # risk at most this % of equity per trade

# Paper trading — set to true to simulate orders without hitting Zerodha
PAPER_TRADING=false

# Monitoring — optional Telegram alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Dashboard (optional)
DASHBOARD_ENABLED=true
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080

# Algo configuration — JSON list; omit to use all instruments in the DB
# ALGOS='[{"name":"momentum","instruments":["INFY","TCS"],"equity":100000}]'
```

> **Zerodha Redirect URL:** In your Kite developer app settings, set the redirect URL to `http://127.0.0.1:8080/` so the login script can capture the request token automatically.

### 3. Start infrastructure

```bash
docker compose up postgres redis -d
```

### 4. Run database migrations

Migrations run automatically on bot startup, but you can apply them manually:

```bash
uv run alembic upgrade head
```

---

## Daily Login (access token refresh)

Zerodha access tokens expire daily. Run this each morning before market open:

```bash
uv run python -m trading.scripts.login
```

This opens a browser to the Kite login page, captures the redirect, and writes `ZERODHA_ACCESS_TOKEN` to `.env` automatically.

---

## Running the Bot

```bash
uv run python main.py
```

The bot will:
1. Apply any pending DB migrations
2. Start the APScheduler
3. Fire `Runtime.start` at **09:15 IST** each weekday
4. Fire `Runtime.stop` at **15:30 IST** each weekday
5. If started during market hours, begin trading immediately

Stop with `Ctrl+C` — shuts down cleanly (scheduler stopped, DB/Redis connections closed).

### Running with Docker Compose (all services including the bot)

```bash
docker compose up --build
```

---

## Monitoring Dashboard

When `DASHBOARD_ENABLED=true`, a live portfolio dashboard is available.

| How you're running | URL |
|--------------------|-----|
| `uv run python main.py` directly | `http://127.0.0.1:8080` |
| `docker compose up` | `http://localhost:8080` |

When running via Docker Compose, the dashboard binds to `0.0.0.0` inside the container (set via `DASHBOARD_HOST` in `docker-compose.yml`) and port 8080 is mapped to your laptop, so `http://localhost:8080` works directly in your browser.

If you want a different host port (e.g. to avoid conflicts), change the mapping in `docker-compose.yml`:

```yaml
ports:
  - "9090:8080"   # access at http://localhost:9090
```

---

## Testing

All three test suites use `pytest` via `uv run`. Run them from inside their respective directories.

### Unit tests

Fast, no external services needed (uses `fakeredis` and `aiosqlite`).

```bash
cd trading-platform
uv run pytest tst/
```

### Strategy tests (backtesting, Monte Carlo, walk-forward)

Requires Docker (uses `testcontainers` to spin up Postgres and Redis).

```bash
cd trading-platform/strategy-testing
uv sync
uv run pytest strategy-testing/
```

Individual suites:

```bash
uv run pytest strategy-testing/test_backtest.py            # backtesting
uv run pytest strategy-testing/test_walk_forward.py        # walk-forward analysis
uv run pytest strategy-testing/test_monte_carlo.py         # Monte Carlo simulation
uv run pytest strategy-testing/test_parameter_sensitivity.py
uv run pytest strategy-testing/test_stress.py
```

### System / integration tests

Requires Docker. Spins up full infrastructure and tests broker failure, order lifecycle, risk guardrails, and state recovery.

```bash
cd trading-platform/system-testing
uv sync
uv run pytest system-testing/
```

---

## Project Layout

```
trading-platform/
├── main.py                         # entrypoint
├── src/trading/
│   ├── config/settings.py          # all config via pydantic-settings + .env
│   ├── core/                       # models, schemas, DB engine, Redis messaging
│   ├── broker/                     # broker abstractions, Zerodha and paper broker
│   ├── engine/                     # component lifecycle, algo runner, scheduler, heartbeat
│   ├── execution/                  # order executor with idempotency
│   ├── data/                       # candle loading (Polars) and realtime feed
│   ├── features/                   # technical indicators (EMA, RSI, ATR, VWAP)
│   ├── strategy/                   # strategy base + EMA crossover example
│   ├── risk/                       # risk rules, position sizer, controller
│   ├── storage/                    # repository (orders, positions, trades)
│   ├── monitoring/                 # Telegram alerts, dashboard
│   ├── di/                         # Dishka DI container and providers
│   └── scripts/login.py            # daily Zerodha token refresh
├── tst/unit/                       # unit tests
├── alembic/                        # DB migrations
├── strategy-testing/               # backtesting / Monte Carlo / walk-forward framework
└── system-testing/                 # Docker-based integration tests
```
