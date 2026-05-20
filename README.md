# algo-trader

Infrastructure and orchestration for a live algorithmic trading system targeting Indian equity markets (NSE) via the Zerodha/Kite broker.

This repo contains only the root-level glue: `docker-compose.yml` for production deployment and `dev.py`/`dev.ps1` for local development. The actual application code lives in three separate repos:

| Repo | Description |
|------|-------------|
| [trading-platform](https://github.com/SakethThogarucheeti/trading-platform) | Python trading engine, strategy execution, and REST API |
| [trading-dashboard](https://github.com/SakethThogarucheeti/trading-dashboard) | Next.js live monitoring dashboard |
| [quantindicators](https://github.com/SakethThogarucheeti/quantindicators) | Polars-based technical indicator library |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    algo-trader                       │
│  docker-compose.yml  ·  dev.py  ·  dev.ps1          │
└──────────────┬────────────────────┬─────────────────┘
               │                    │
    ┌──────────▼──────────┐  ┌──────▼──────────────┐
    │  trading-platform   │  │  trading-dashboard   │
    │  Python / FastAPI   │◄─┤  Next.js / React     │
    │  :8081              │  │  :3000               │
    └──────────┬──────────┘  └─────────────────────-┘
               │
    ┌──────────▼──────────┐   ┌────────────────────┐
    │     PostgreSQL 16   │   │      Redis 7        │
    │     :5432           │   │      :6379          │
    └─────────────────────┘   └────────────────────┘
```

The trading-platform polls Zerodha's KiteConnect WebSocket for live tick data, runs strategy logic, and persists decisions to Postgres. The dashboard reads from the same API. Redis is used for pub/sub between internal components.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js 20+
- Docker + Docker Compose v2+
- Zerodha developer account — [create an app](https://developers.kite.trade/apps) and set the redirect URL to `http://127.0.0.1:8080/`

## Setup

**1. Clone all repos into the same parent directory:**

```bash
git clone https://github.com/SakethThogarucheeti/algo-trader
git clone https://github.com/SakethThogarucheeti/trading-platform
git clone https://github.com/SakethThogarucheeti/trading-dashboard
git clone https://github.com/SakethThogarucheeti/quantindicators
```

Your directory structure should look like:

```
workspace/
├── algo-trader/
├── trading-platform/
├── trading-dashboard/
└── quantindicators/
```

**2. Install dependencies:**

```bash
cd trading-platform && uv sync
cd ../trading-dashboard && npm ci
```

**3. Configure environment:**

```bash
cp trading-platform/.env.example trading-platform/.env
# Fill in ZERODHA_API_KEY and ZERODHA_API_SECRET
```

```bash
cp trading-dashboard/.env.local.example trading-dashboard/.env.local
```

## Running

### Local development (hot reload)

```bash
cd algo-trader

# Linux/macOS
python dev.py

# Windows
.\dev.ps1
```

This starts Postgres and Redis via Docker, then launches both the trading-platform and trading-dashboard with hot reload.

### Production (Docker)

```bash
cd algo-trader
docker compose up --build
```

| Service | URL |
|---------|-----|
| Trading API + dashboard backend | http://localhost:8081 |
| Trading dashboard UI | http://localhost:3000 |

### Daily token refresh (required for live trading)

Zerodha access tokens expire daily. Before 09:15 IST each trading day, run:

```bash
cd trading-platform
uv run python -m trading.scripts.login
```

This opens a browser for OAuth and writes the new token to `.env`.
