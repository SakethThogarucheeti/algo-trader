# algo-trader

Infrastructure and orchestration for a live algorithmic trading system targeting Indian equity markets (NSE) via the Zerodha/Kite broker.

This repo contains only the root-level glue: `docker-compose.yml` for production deployment and `dev.py`/`dev.ps1` for local development. The two services it runs are separate repos, cloned as siblings:

| Repo | Description |
|------|-------------|
| [trading-platform](https://github.com/SakethThogarucheeti/trading-platform) | Python trading engine — pipeline orchestration, broker adapters, REST API. A thin wrapper: strategy and risk-filter *content* live in the SDKs below, not here. |
| [trading-dashboard](https://github.com/SakethThogarucheeti/trading-dashboard) | React (TanStack Start) live monitoring dashboard — proxies all data through trading-platform's API, no backend of its own |

trading-platform pulls in the rest of its own dependency tree as pinned packages — none of these need to be cloned separately:

| Package | Description |
|---------|-------------|
| [trading-types](https://github.com/SakethThogarucheeti/trading-types) | Shared domain types (event models, enums, `Clock`) — the common root every other package depends on |
| [quantindicators](https://github.com/SakethThogarucheeti/quantindicators) | Polars-based technical indicator library |
| [trading-strategy-sdk](https://github.com/SakethThogarucheeti/trading-strategy-sdk) | `Strategy` ABC, concrete strategies, factory registry |
| [trading-risk-sdk](https://github.com/SakethThogarucheeti/trading-risk-sdk) | Risk gates, position sizer, policy protocols |

Two more sibling repos round out the workspace — neither is part of the runtime services this repo orchestrates, but both are useful to have checked out alongside them:

| Repo | Description |
|------|-------------|
| [trading-integ-tests](https://github.com/SakethThogarucheeti/trading-integ-tests) | Backtesting, Monte Carlo, walk-forward, and system-level integration tests. Path-depends on trading-platform (editable local install), so it must be cloned as a sibling directory, not pulled in via `uv sync`. |
| [trading-research](https://github.com/SakethThogarucheeti/trading-research) | Standalone CLI (`research backtest` / `walk-forward` / `monte-carlo`) for strategy research, driving the same trading-platform pipeline classes against pinned package versions. Shareable independently of this workspace — no path deps. |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    algo-trader                       │
│  docker-compose.yml  ·  dev.py  ·  dev.ps1          │
└──────────────┬────────────────────┬─────────────────┘
               │                    │
    ┌──────────▼──────────┐  ┌──────▼──────────────┐
    │  trading-platform   │  │  trading-dashboard   │
    │  Python / FastAPI   │◄─┤  React / TanStack    │
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

### Just running the live system

**1. Clone the two service repos into the same parent directory:**

```bash
git clone https://github.com/SakethThogarucheeti/algo-trader
git clone https://github.com/SakethThogarucheeti/trading-platform
git clone https://github.com/SakethThogarucheeti/trading-dashboard
```

`quantindicators`, `trading-types`, `trading-strategy-sdk`, and `trading-risk-sdk` do **not** need cloning — `uv sync` pulls them automatically as pinned git dependencies of trading-platform.

Your directory structure should look like:

```
workspace/
├── algo-trader/
├── trading-platform/
└── trading-dashboard/
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

### Full workspace (research, integration tests, or SDK development)

Clone whichever of these you need as additional siblings of `algo-trader`:

```bash
git clone https://github.com/SakethThogarucheeti/trading-integ-tests
git clone https://github.com/SakethThogarucheeti/trading-research

# only needed if you're developing the SDKs/libraries themselves, not just
# consuming them — otherwise uv sync pulls pinned versions automatically
git clone https://github.com/SakethThogarucheeti/trading-types
git clone https://github.com/SakethThogarucheeti/quantindicators
git clone https://github.com/SakethThogarucheeti/trading-strategy-sdk
git clone https://github.com/SakethThogarucheeti/trading-risk-sdk
```

Full workspace layout:

```
workspace/
├── algo-trader/
├── trading-platform/
├── trading-dashboard/
├── trading-integ-tests/
├── trading-research/
├── trading-types/
├── quantindicators/
├── trading-strategy-sdk/
└── trading-risk-sdk/
```

Each has its own `uv sync`:

```bash
cd trading-integ-tests/strategy && uv sync   # path-depends on trading-platform, editable
cd ../../trading-research && uv sync          # pinned deps, fully standalone
```

The four SDK/library repos (`trading-types`, `quantindicators`, `trading-strategy-sdk`, `trading-risk-sdk`) are plain `uv` packages — `cd <repo> && uv sync` and edit as normal. They aren't wired into the other repos via local paths, so a change made there won't be picked up elsewhere until it's tagged and the consuming repo's pin (in `pyproject.toml` under `[tool.uv.sources]`) is bumped to the new tag.

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
