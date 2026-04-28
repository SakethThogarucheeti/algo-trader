# algo-trader

An event-driven intraday trading platform for Indian equity markets, built on Zerodha/Kite.

**Architecture:** Redis pub/sub messaging · PostgreSQL persistence · APScheduler market-hours automation · Dishka DI · async-first (anyio)

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Starting the Bot](#starting-the-bot)
- [Monitoring Dashboard](#monitoring-dashboard)
- [Testing](#testing)
- [System Architecture](#system-architecture)
- [Tick-to-Fill Walkthrough](#tick-to-fill-walkthrough)
- [Project Layout](#project-layout)
- [Adding a New Strategy](#adding-a-new-strategy)
- [Key Design Decisions](#key-design-decisions)

---

## Prerequisites

| Tool                             | Version | Notes                               |
| -------------------------------- | ------- | ----------------------------------- |
| Python                           | 3.13+   | managed by uv via `.python-version` |
| [uv](https://docs.astral.sh/uv/) | latest  | dependency manager and runner       |
| Docker + Docker Compose          | v2+     | for Postgres and Redis              |

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

# Capital allocated to the default algo (used when ALGOS is not set)
DEFAULT_EQUITY=10000

# Algo configuration — JSON list; omit to use all instruments in the DB with DEFAULT_EQUITY
# ALGOS='[{"name":"momentum","instruments":["INFY","TCS"],"equity":10000}]'
```

> **Zerodha Redirect URL:** In your Kite developer app settings, set the redirect URL to `http://127.0.0.1:8080/` so the login script can capture the request token automatically.

### 3. Daily login (access token refresh)

Zerodha access tokens expire daily. Run this each morning before market open:

```bash
uv run python -m trading.scripts.login
```

This opens a browser to the Kite login page, captures the redirect, and writes `ZERODHA_ACCESS_TOKEN` to `.env` automatically.

---

## Starting the Bot

### One command (recommended)

```bash
uv run start
```

This single command:

1. Starts Postgres and Redis via Docker Compose
2. Waits until both are healthy
3. Launches the trading bot

### Manual steps (if you prefer)

```bash
# 1. Start infrastructure
docker compose up postgres redis -d

# 2. Wait until healthy, then start the bot
uv run python main.py
```

The bot will:

1. Apply any pending DB migrations automatically
2. Start the APScheduler
3. Fire `Runtime.start` at **09:15 IST** each weekday
4. Fire `Runtime.stop` at **15:30 IST** each weekday
5. If started during market hours, begin trading immediately

Stop with `Ctrl+C` — shuts down cleanly (scheduler stopped, DB/Redis connections closed).

### Running everything in Docker (bot + infra)

```bash
docker compose up --build
```

---

## Monitoring Dashboard

When `DASHBOARD_ENABLED=true`, a live portfolio dashboard is available.

| How you're running               | URL                     |
| -------------------------------- | ----------------------- |
| `uv run python main.py` directly | `http://127.0.0.1:8080` |
| `docker compose up`              | `http://localhost:8080` |

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
uv run pytest strategy-testing/test_hyperparam_search.py   # EMA crossover grid search
uv run pytest strategy-testing/test_vwap_search.py         # VWAP reversion grid search
uv run pytest strategy-testing/test_rsi_search.py          # RSI mean-reversion grid search
uv run pytest strategy-testing/test_orb_search.py          # Opening range breakout grid search
```

### System / integration tests

Requires Docker. Spins up full infrastructure and tests broker failure, order lifecycle, risk guardrails, and state recovery.

```bash
cd trading-platform/system-testing
uv sync
uv run pytest system-testing/
```

---

## System Architecture

The system is fully event-driven. Components never call each other directly — they publish and subscribe to named channels on the message bus. This means every layer is independently replaceable and testable.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            LIVE TRADING                                 │
│                                                                         │
│  Zerodha WebSocket                                                      │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────────┐    tick:{token}   ┌───────────────────┐             │
│  │ KiteIngestor │ ────────────────► │ CandleAggregator  │             │
│  │  (Component) │                   │    (Component)    │             │
│  └──────────────┘                   └─────────┬─────────┘             │
│   • validates tick                            │ candle:{symbol}:{interval}
│   • writes TickLog                            ▼                        │
│   • updates PriceStore              ┌───────────────────┐             │
│   • circuit breaker                 │    AlgoRunner     │             │
│                                     │   (Component)     │             │
│                                     └─────────┬─────────┘             │
│                                               │ • updates FeatureEngine│
│                                               │ • calls strategy       │
│                                               │ signals:{algo_name}    │
│                                               ▼                        │
│                                     ┌───────────────────┐             │
│                                     │  RiskController   │             │
│                                     │   (Component)     │             │
│                                     └─────────┬─────────┘             │
│                                               │ validated_orders:{algo}│
│                                               ▼                        │
│                                     ┌───────────────────┐             │
│                                     │  OrderExecutor    │             │
│                                     │   (Component)     │             │
│                                     └─────────┬─────────┘             │
│                                               │                        │
│                                      ┌────────┴────────┐              │
│                                      │  Zerodha REST   │              │
│                                      │  (place_order)  │              │
│                                      └────────┬────────┘              │
│                                               │ postback webhook       │
│                                               ▼                        │
│                                     ┌───────────────────┐             │
│                                     │   Fill Handler    │             │
│                                     │ (update position) │             │
│                                     └───────────────────┘             │
│                                                                         │
│  All components share:  MessageBus (Redis)  ·  Repository (Postgres)  │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Overview

| Component                | File                    | What it does                                                                                                                                                                                                                                       |
| ------------------------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `KiteIngestor`           | `data/realtime.py`      | Bridges the Zerodha WebSocket to the async event loop. Writes every tick to `tick_logs`, assigns a `tick_log_id`, and publishes a `TickEvent`. Sets a circuit-breaker flag if disconnected for more than 30 seconds.                               |
| `CandleAggregator`       | `data/candles.py`       | Subscribes to `tick:{token}` for every instrument. Maintains a partial bar per (symbol, interval) and emits a `CandleEvent` when the bar window closes. On startup, fetches historical candles from the broker to warm up the feature engine.      |
| `AlgoRunner`             | `engine/algo_runner.py` | One per configured algo. Subscribes to `candle:{symbol}:{interval}`, feeds each candle to the `FeatureEngine` to compute indicators, then calls `strategy.on_candle()`. If the strategy returns a signal it is published to `signals:{algo_name}`. |
| `TechnicalFeatureEngine` | `features/technical.py` | Maintains a rolling Polars DataFrame per (symbol, interval). On each `update()` call it appends the new bar and recomputes EMA, RSI, ATR, and session VWAP using pure Polars expressions. No TA-Lib dependency.                                    |
| `Strategy`               | `strategy/base.py`      | Abstract base. `on_candle(symbol, instrument_type, df)` receives the indicator-enriched DataFrame and returns a `Signal` or `None`. Stateless — no DB or bus access.                                                                               |
| `RiskController`         | `risk/controller.py`    | Subscribes to `signals:{algo_name}`. Runs a 5-step rejection pipeline. Accepted signals become `ValidatedOrderEvent` and are published to `validated_orders:{algo_name}`.                                                                          |
| `OrderExecutor`          | `execution/executor.py` | Subscribes to `validated_orders:{algo_name}`. Delegates to `ExecutionEngine.execute()` which persists the order, calls the broker, and handles fills.                                                                                              |
| `HeartbeatMonitor`       | `engine/heartbeat.py`   | Writes its own heartbeat to Postgres every N seconds and checks all other modules. Fires a Telegram alert when any module goes stale.                                                                                                              |
| `Runtime`                | `engine/runtime.py`     | Supervises all components with ordered startup (each component's `_setup()` completes before the next one starts) and reverse-order shutdown.                                                                                                      |
| `Scheduler`              | `engine/scheduler.py`   | Uses APScheduler to fire `Runtime.start` at 09:15 IST and `Runtime.stop` at 15:30 IST on weekdays.                                                                                                                                                 |

### Message Bus Channels

| Channel                        | Event type             | Published by       | Consumed by                   |
| ------------------------------ | ---------------------- | ------------------ | ----------------------------- |
| `tick:{instrument_token}`      | `TickEvent`            | `KiteIngestor`     | `CandleAggregator`            |
| `candle:{symbol}:{interval}`   | `CandleEvent`          | `CandleAggregator` | `AlgoRunner`                  |
| `signals:{algo_name}`          | `SignalEvent`          | `AlgoRunner`       | `RiskController`              |
| `validated_orders:{algo_name}` | `ValidatedOrderEvent`  | `RiskController`   | `OrderExecutor`               |
| `orders:{algo_name}`           | `OrderEvent`           | `OrderExecutor`    | (audit / monitoring)          |
| `fills:{algo_name}`            | `FillEvent`            | `OrderExecutor`    | (equity tracking, monitoring) |
| `testing:progress`             | `SessionProgressEvent` | `BacktestSession`  | (test harness)                |

### Risk Pipeline

Every signal passes through five rejection gates in order:

```
SignalEvent
    │
    ├─ 1. Intraday cutoff      reject after 15:30 IST (configurable)
    ├─ 2. Circuit breaker      reject if WebSocket disconnected > 30s
    ├─ 3. Daily loss limit     reject if today's realized PnL ≥ max_daily_loss_pct × equity
    │                          (skipped in paper trading / backtesting)
    ├─ 4. Duplicate position   reject ENTRY if already long/short same direction
    │                          (opposite direction = reversal, allowed through)
    └─ 5. Quantity sizing      reject if ATR-based position size rounds to 0
             │
             └─► ValidatedOrderEvent  (quantity already determined)
```

Position sizing formula:

```
qty = floor( (equity × risk_per_trade_pct / 100) / stop_distance )
```

`stop_distance` comes from the strategy (typically `atr_multiplier × ATR`), so the system automatically risks the same percentage of equity regardless of volatility.

### Persistence Model

Every event that flows through the pipeline leaves a trace in Postgres:

| Table           | Written by                                         | Purpose                                         |
| --------------- | -------------------------------------------------- | ----------------------------------------------- |
| `tick_logs`     | `KiteIngestor`                                     | Immutable record of every raw market tick       |
| `decision_logs` | `CandleAggregator`, `AlgoRunner`, `RiskController` | Full audit trail — one row per pipeline step    |
| `signals`       | `RiskController`                                   | Accepted signal parameters                      |
| `orders`        | `OrderExecutor`                                    | Order lifecycle (PENDING → PLACED → FILLED)     |
| `positions`     | `OrderExecutor`                                    | Live net position per (symbol, instrument_type) |
| `heartbeats`    | `HeartbeatMonitor`                                 | Module liveness timestamps                      |
| `audit_logs`    | `RiskController`, `OrderExecutor`                  | Free-form operational events                    |

Every event carries a `tick_log_id` that propagates from the original tick all the way to the fill. A single query on `decision_logs WHERE tick_log_id = X` reconstructs the full causal chain for any trade.

### Broker Abstraction

The `Broker` and `BrokerStream` ABCs allow the execution layer to be swapped without touching any strategy or risk code:

| Mode          | Broker                                                 | BrokerStream                       |
| ------------- | ------------------------------------------------------ | ---------------------------------- |
| Live trading  | `ZerodhaBroker` (REST via KiteClient)                  | `ZerodhaStream` (WebSocket)        |
| Paper trading | `PaperBroker` (wraps real broker, fakes `place_order`) | `ZerodhaStream` (real market data) |
| Backtesting   | `SlippageFillSimulator`                                | `CandlePlayer` (file replay)       |

### Dependency Injection

The system uses [Dishka](https://github.com/reagento/dishka) for DI. Everything is assembled in three providers:

- **`InfrastructureProvider`** — singletons: Settings, AsyncEngine, Redis, `RedisMessageBus`, `Repository`, `PriceStore`
- **`BrokerProvider`** — `ZerodhaBroker` (or `PaperBroker`), `ZerodhaStream`, `KiteClient`
- **`ComponentProvider`** — one `AlgoRunner` + `RiskController` + `OrderExecutor` per algo config; shared `KiteIngestor`, `CandleAggregator`, `HeartbeatMonitor`, `Runtime`, `Scheduler`

Every component depends only on abstract interfaces (`MessageBus`, `AbstractRepository`, `AbstractPriceStore`, `AbstractRuntime`). The concrete implementations are only named at the composition root inside the providers.

### Backtesting

The backtest reuses every live component — `AlgoRunner`, `RiskController`, `DirectExecutionEngine` — with only the data source and broker swapped:

| Live                                  | Backtest                                      |
| ------------------------------------- | --------------------------------------------- |
| `ZerodhaStream` WebSocket             | `CandlePlayer` replaying Parquet files        |
| `ZerodhaBroker.place_order()`         | `SlippageFillSimulator.place_order()`         |
| `RedisMessageBus` (Redis round-trips) | `LocalMessageBus` (in-process, zero overhead) |
| `SystemClock` (wall time)             | `SimulatedClock` (bar timestamps)             |
| Real Postgres schema                  | Isolated per-run Postgres schema              |

Because the same strategy and risk code runs in both modes, backtest results directly reflect live behaviour.

---

## Tick-to-Fill Walkthrough

This traces a single INFY tick from the Zerodha WebSocket all the way to a filled order, showing exactly which code runs at each step.

**Scenario:** INFY is trading at 1,520. A new 15-minute bar closes at 1,523, and the EMA-9 has just crossed above EMA-21 for the first time.

---

### Step 1 — Tick arrives from Zerodha WebSocket

```
Zerodha WebSocket thread
  └── ZerodhaStream._on_ticks(raw_ticks)
        └── loop.call_soon_threadsafe(_handle_tick, raw)
```

`KiteIngestor._handle_tick()` runs on the async event loop:

```python
# data/realtime.py — KiteIngestor._handle_tick()
async with get_session(self._session_factory) as session:
    tick_log_id = await self._repo.log_tick(session, event, symbol)
    # flush() assigns the DB row id without waiting for a full commit
```

A `TickLog` row is written (`instrument_token=12345, last_price=1523.0, received_at=now`).
The auto-incremented `id` (say, **42**) is returned immediately.

```python
event = TickEvent(
    instrument_token=12345, last_price=1523.0, volume=8400,
    timestamp=now, tick_log_id=42          # ← propagated from here
)
await self._bus.publish("tick:12345", event)
self._price_store.update("INFY", 1523.0)  # keeps PriceStore current
```

**State after step 1:**

- `tick_logs` row id=42
- `PriceStore["INFY"] = 1523.0`
- `TickEvent(tick_log_id=42)` on Redis channel `tick:12345`

---

### Step 2 — Candle bar closes

`CandleAggregator` is subscribed to `tick:12345`. Its handler fires:

```python
# data/candles.py — CandleAggregator._process_tick()
bar_open = _bar_open_time(event.timestamp, interval="15min")
# bar_open = 09:15:00 — same bar as the previous tick

partial = self._bars[("INFY", "15min")]
partial.close = 1523.0
partial.high = max(partial.high, 1523.0)
partial.volume += 8400
```

The _next_ tick (09:30:00) will have a different `bar_open`, which triggers:

```python
# Emit the completed bar
candle = CandleEvent(
    symbol="INFY", interval="15min",
    open=1498.0, high=1525.0, low=1495.0, close=1523.0, volume=142000,
    timestamp=bar_open,
    tick_log_id=42      # ← the tick that closed the bar
)
await self._bus.publish("candle:INFY:15min", candle)
await self._repo.log_decision(session, step="CANDLE_EMITTED", symbol="INFY",
                               tick_log_id=42, context={...})
```

**State after step 2:**

- `decision_logs` row: `step=CANDLE_EMITTED, tick_log_id=42`
- `CandleEvent(tick_log_id=42)` on Redis channel `candle:INFY:15min`

---

### Step 3 — Feature engine updates, strategy fires

`AlgoRunner` is subscribed to `candle:INFY:15min`. Its handler fires:

```python
# engine/algo_runner.py — AlgoRunner._on_candle()
df = self._feature_engine.update(event)
# df is now a 200-row Polars DataFrame with columns:
#   timestamp, open, high, low, close, volume,
#   ema_9, ema_21, rsi_14, atr_14, vwap
```

`TechnicalFeatureEngine.update()` appends the new bar and recomputes all indicators in two Polars passes (session ID for VWAP grouping, then all indicator expressions). The last two rows of the result look like:

```
timestamp   close   ema_9    ema_21   atr_14
09:00       1498    1495.2   1501.4   8.3     ← ema_9 below ema_21
09:15       1523    1502.1   1501.9   8.6     ← ema_9 now above ema_21 ✓
```

The strategy sees the crossover:

```python
# strategy/examples/ema_crossover.py — EmaCrossoverStrategy.on_candle()
prev_fast, cur_fast = 1495.2, 1502.1
prev_slow, cur_slow = 1501.4, 1501.9

# Crossover: was below, now above → BUY signal
if prev_fast < prev_slow and cur_fast > cur_slow:
    return Signal(
        symbol="INFY", side=Side.BUY, strategy_id="ema_crossover",
        signal_type=SignalType.ENTRY,
        stop_distance=1.5 * 8.6   # atr_multiplier × ATR = 12.9
    )
```

`AlgoRunner` converts the `Signal` to a `SignalEvent` and publishes it:

```python
signal_event = SignalEvent(
    symbol="INFY", side=BUY, stop_distance=12.9,
    tick_log_id=42,    # ← still propagating
    signal_id=UUID("a1b2...")
)
await self._bus.publish("signals:momentum", signal_event)
await self._repo.log_decision(session, step="SIGNAL_GENERATED", ...)
```

**State after step 3:**

- `decision_logs` row: `step=SIGNAL_GENERATED, tick_log_id=42, signal_id=a1b2...`
- `SignalEvent(tick_log_id=42)` on Redis channel `signals:momentum`

---

### Step 4 — Risk controller validates the signal

`RiskController` is subscribed to `signals:momentum`. It runs five checks:

```python
# risk/controller.py — DefaultRiskController._evaluate_signal()

# 1. Time check — 09:15 IST, well before the 15:30 cutoff ✓
# 2. Circuit breaker — flag not set ✓
# 3. Daily loss limit — paper_trading=False, today's PnL = 0, limit = 2,000 ✓
# 4. Position check — no existing INFY position ✓
# 5. Quantity sizing:
qty = floor((100_000 × 1.0 / 100) / 12.9) = floor(775.2) = 775
# qty = 775, lot_size=1 (equity) → 775 ✓
```

Signal accepted. A `ValidatedOrderEvent` is published:

```python
await self._repo.save_signal(session, signal_event)   # persist Signal row
validated = ValidatedOrderEvent(
    signal_id=UUID("a1b2..."), symbol="INFY",
    side=BUY, quantity=775, order_type=MARKET,
    tick_log_id=42
)
await self._bus.publish("validated_orders:momentum", validated)
await self._repo.log_decision(session, step="SIGNAL_ACCEPTED", ...)
```

**State after step 4:**

- `signals` row: `id=a1b2..., symbol=INFY, side=BUY, stop_distance=12.9`
- `decision_logs` row: `step=SIGNAL_ACCEPTED, tick_log_id=42`
- `ValidatedOrderEvent` on Redis channel `validated_orders:momentum`

---

### Step 5 — Order executor places the order

`OrderExecutor` is subscribed to `validated_orders:momentum`. It delegates to `DirectExecutionEngine.execute()`:

```python
# execution/executor.py — DirectExecutionEngine.execute()

# 1. Idempotency: no existing Order for signal_id a1b2... → proceed

# 2. Persist PENDING order (before broker call, so no ghost orders)
order = Order(id=UUID("c3d4..."), kite_order_id=None,
              signal_id=UUID("a1b2..."), status=PENDING, qty=775)
await self._repo.save_order(session, order)

# 3. Register fill-tracking callback synchronously (before any FillEvent can arrive)
self._on_order_placed("KITE_ORDER_789", "INFY", Side.BUY)

# 4. Place the order (async REST call to Zerodha)
kite_order_id = await self._broker.place_order(
    symbol="INFY", side=BUY, qty=775, order_type=MARKET
)
# kite_order_id = "KITE_ORDER_789"

# 5. Update order status to PLACED
await self._repo.update_order_status(session, "KITE_ORDER_789", PLACED)

# 6. Publish OrderEvent
await self._bus.publish("orders:momentum", OrderEvent(...))
```

**State after step 5:**

- `orders` row: `kite_order_id=KITE_ORDER_789, status=PLACED, qty=775`

---

### Step 6 — Fill arrives (Zerodha postback webhook)

Zerodha sends a fill notification via HTTP postback. The webhook calls `handle_fill()`:

```python
# execution/executor.py — DirectExecutionEngine.handle_fill()
async with self._session_factory() as session:
    async with session.begin():
        # Atomic: order update + position update in a single transaction
        await self._repo.update_order_status(
            session, "KITE_ORDER_789", FILLED, avg_price=1523.50
        )
        await self._repo.update_position(
            session, fill=fill_event, side=BUY,
            symbol="INFY", instrument_type="EQUITY"
        )
        # Position upsert with SELECT FOR UPDATE (safe under concurrent fills)
        # net_qty: 0 + 775 = 775, avg_price: 1523.50

fill_event = FillEvent(
    kite_order_id="KITE_ORDER_789",
    avg_price=1523.50, filled_qty=775,
    tick_log_id=42
)
await self._bus.publish("fills:momentum", fill_event)
```

**Final state in Postgres:**

| Table           | Row                                                                    |
| --------------- | ---------------------------------------------------------------------- |
| `tick_logs`     | id=42, symbol=INFY, last_price=1523.0                                  |
| `decision_logs` | CANDLE_EMITTED, SIGNAL_GENERATED, SIGNAL_ACCEPTED — all tick_log_id=42 |
| `signals`       | id=a1b2..., side=BUY, stop_distance=12.9                               |
| `orders`        | id=c3d4..., status=FILLED, avg_price=1523.50, qty=775                  |
| `positions`     | symbol=INFY, net_qty=775, avg_price=1523.50                            |

To reconstruct the full decision chain for this trade:

```sql
SELECT step, algo_name, context, created_at
FROM decision_logs
WHERE tick_log_id = 42
ORDER BY created_at;
```

---

## Project Layout

```
trading-platform/
├── main.py                              # entry point
├── src/trading/
│   ├── config/
│   │   ├── settings.py                  # all config via pydantic-settings + .env
│   │   └── strategy_config.py           # strategy_config.json loader
│   ├── core/
│   │   ├── models.py                    # SQLAlchemy ORM models
│   │   ├── schemas.py                   # Pydantic event models (TickEvent → FillEvent)
│   │   ├── messaging.py                 # MessageBus ABC + RedisMessageBus
│   │   ├── database.py                  # engine factory, session helpers
│   │   └── clock.py                     # Clock ABC, SystemClock, SimulatedClock
│   ├── broker/
│   │   ├── base/broker.py               # Broker ABC
│   │   ├── base/broker_stream.py        # BrokerStream ABC
│   │   ├── zerodha_broker/              # ZerodhaBroker + ZerodhaStream (live)
│   │   └── paper_broker.py              # PaperBroker + AbstractPriceStore + PriceStore
│   ├── data/
│   │   ├── realtime.py                  # KiteIngestor — WebSocket → TickEvent
│   │   └── candles.py                   # CandleAggregator — TickEvent → CandleEvent
│   ├── features/
│   │   ├── base.py                      # FeatureEngine ABC
│   │   └── technical.py                 # TechnicalFeatureEngine (EMA, RSI, ATR, VWAP)
│   ├── strategy/
│   │   ├── base.py                      # Strategy ABC + Signal dataclass
│   │   └── examples/
│   │       ├── ema_crossover.py         # EMA crossover strategy
│   │       ├── rsi_mean_reversion.py    # RSI mean-reversion strategy
│   │       ├── vwap_reversion.py        # VWAP reversion strategy
│   │       └── opening_range_breakout.py
│   ├── risk/
│   │   ├── base.py                      # RiskController ABC
│   │   ├── controller.py                # DefaultRiskController (5-step pipeline)
│   │   └── sizer.py                     # ATR-based position sizer
│   ├── execution/
│   │   ├── base.py                      # ExecutionEngine ABC
│   │   ├── executor.py                  # DirectExecutionEngine + OrderExecutor
│   │   └── idempotency.py               # signal_id duplicate detection
│   ├── engine/
│   │   ├── component.py                 # Component ABC (CREATED→RUNNING→STOPPED)
│   │   ├── runtime.py                   # AbstractRuntime + Runtime (ordered lifecycle)
│   │   ├── algo_runner.py               # AlgoRunner — candle → features → strategy → signal
│   │   ├── scheduler.py                 # APScheduler market-hours integration
│   │   └── heartbeat.py                 # HeartbeatMonitor + Telegram alerts
│   ├── storage/
│   │   ├── base.py                      # AbstractRepository
│   │   └── repository.py                # Repository (all DB operations)
│   ├── monitoring/
│   │   ├── telegram.py                  # TelegramAlerter
│   │   └── dashboard/                   # Live portfolio dashboard (aiohttp)
│   ├── di/
│   │   ├── container.py                 # Dishka container builder
│   │   └── providers/
│   │       ├── infra.py                 # Settings, DB, Redis, MessageBus, Repository
│   │       ├── broker.py                # Broker, BrokerStream, KiteClient
│   │       ├── components.py            # Runtime, AlgoRunner, RiskController, etc.
│   │       ├── execution.py             # make_execution_engine() factory
│   │       ├── risk.py                  # make_risk_controller() factory
│   │       ├── features.py              # make_feature_engine() factory
│   │       └── strategy.py              # make_strategy() factory
│   └── scripts/
│       ├── login.py                     # daily Zerodha token refresh
│       └── fetch_data.py                # download historical OHLCV to Parquet
├── alembic/                             # DB migrations
├── tst/unit/                            # unit tests (fakeredis + aiosqlite)
├── strategy-testing/
│   ├── testing/
│   │   ├── backtesting/engine.py        # BacktestSession
│   │   ├── backtesting/metrics.py       # Sharpe, CAGR, max drawdown, etc.
│   │   ├── local_bus.py                 # LocalMessageBus (in-process, no Redis)
│   │   ├── monte_carlo/                 # Monte Carlo simulation
│   │   └── simulators/
│   │       ├── candle_player.py         # replays Parquet files as CandleEvents
│   │       └── execution_sim.py         # SlippageFillSimulator
│   └── strategy-testing/               # test files (grid searches, walk-forward)
├── system-testing/                      # Docker-based integration tests
├── strategy_config.json                 # hyperparam search grids + strategy defaults
└── docker-compose.yml
```

---

## Adding a New Strategy

1. **Create the strategy class** in `src/trading/strategy/examples/my_strategy.py`:

```python
from trading.strategy.base import Signal, Strategy
from trading.core.schemas import InstrumentType, Side, SignalType
import polars as pl

class MyStrategy(Strategy):
    @property
    def id(self) -> str:
        return "my_strategy"

    def on_candle(self, symbol, instrument_type, df):
        if df.height < 2:
            return None
        # Your logic here — df has columns: close, ema_9, ema_21, rsi_14, atr_14, vwap
        # Return a Signal or None
        ...
```

2. **Register it** in `src/trading/di/providers/strategy.py`:

```python
case "my_strategy":
    return MyStrategy(**params)
```

3. **Configure it** via the `ALGOS` env var or `strategy_config.json`:

```json
{
  "strategy": { "id": "my_strategy", "params": {} }
}
```

4. **Backtest it** — the existing `BacktestSession` will run it automatically with the same risk and execution logic as live trading.

---

## Key Design Decisions

**Everything is event-driven.** Components communicate only via the message bus. No component holds a reference to another. This makes each layer independently testable and replaceable.

**Every component depends on abstractions.** `MessageBus`, `AbstractRepository`, `AbstractPriceStore`, and `AbstractRuntime` are all ABCs. Concrete implementations (`RedisMessageBus`, `Repository`, `PriceStore`, `Runtime`) are only named inside the DI providers. Swapping a transport or storage backend means adding a new class and changing one line in a provider.

**tick_log_id flows through the entire pipeline.** Every event from `TickEvent` to `FillEvent` carries the `tick_log_id` of the originating market tick. The `decision_logs` table uses it as a foreign key, so a single SQL query on `tick_log_id` reconstructs the complete causal chain: which tick triggered which candle, which candle triggered which signal, which signal was accepted or rejected and why, and which order was placed as a result.

**Backtests reuse live code exactly.** `AlgoRunner`, `RiskController`, and `DirectExecutionEngine` run unchanged in backtests. The only differences are the data source (`CandlePlayer` instead of WebSocket), the broker (`SlippageFillSimulator` instead of Zerodha), the clock (`SimulatedClock` instead of wall time), and the message bus (`LocalMessageBus` instead of Redis). If a strategy behaves differently in backtesting than in live trading, it is a data or timing difference, not a code difference.

**Ordered startup prevents race conditions.** `Runtime` starts components sequentially: each component's `_setup()` must signal readiness before the next one begins. The ingestor is connected and subscribed before the candle aggregator starts listening, which is started before the algo runner subscribes to candles. No component can miss events from its upstream dependency.

**Position updates are atomic.** Order status and position changes happen in a single SQLAlchemy transaction using `SELECT FOR UPDATE`. Concurrent fills for the same symbol cannot race and produce an inconsistent position.
