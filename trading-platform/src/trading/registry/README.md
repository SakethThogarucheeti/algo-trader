# registry

The five pipeline stages that transform a raw WebSocket tick into a filled order. Each registry is a self-contained file with a config `@dataclass` and a single `handle()` method.

## Data flow

```
dict (raw tick)
    │
    ▼  TickRegistry.handle(raw)
TickEvent
    │
    ▼  CandleRegistry.handle(tick)
CandleEvent  (or None — bar still building)
    │
    ▼  AlgoRegistry.handle(candle)
list[SignalEvent]
    │  (one per active strategy that fired)
    ▼  RiskRegistry.handle(signal)
ValidatedOrderEvent  (or None — rejected)
    │
    ▼  ExecRegistry.handle(order)
(side-effect: order placed + position updated)
```

The full wiring is in `pipeline.py` at the project root.

## TickRegistry (`tick.py`)

**Input:** raw Kite tick `dict`  
**Output:** `TickEvent | None`

- Validates required fields and symbol whitelist.
- Writes an immutable `TickLog` row; the returned `tick_log_id` propagates through the entire pipeline for causal tracing.
- Owns the `CircuitBreaker` instance shared with `RiskRegistry`. If the WebSocket has been silent for > 30 s, `circuit.is_open()` returns `True` and risk checks reject all signals.

## CandleRegistry (`candle.py`)

**Input:** `TickEvent`  
**Output:** `CandleEvent | None`

- Builds OHLCV bars in memory. Returns `None` on every tick until the bar closes (i.e., the next tick's timestamp falls into a new bar window).
- Bar-close time is floor-rounded to the interval boundary (e.g., a 14:27 tick closes the 14:15 bar when the 14:30 tick arrives).
- On startup (via `CandleAggregator._setup()`), calls `warmup()` to backfill historical candles from the broker into `PolarsStore` so indicators have enough bars from bar 1.

## AlgoRegistry (`algo.py`)

**Input:** `CandleEvent`  
**Output:** `list[SignalEvent]`

- Maintains one `_AlgoInstance` per `(symbol, strategy_id)` pair.
- Pushes the new candle into `PolarsStore` so indicator `compute()` calls see the latest bar.
- Calls `strategy.on_candle()` — guaranteed pure: no DB writes, no broker calls.
- Returns all signals from all active strategies for that symbol.

## RiskRegistry (`risk.py`)

**Input:** `SignalEvent`  
**Output:** `ValidatedOrderEvent | None`

Five rejection gates in order:

| Gate | Rejects when |
|------|-------------|
| 1. Intraday cutoff | Current time ≥ `intraday_cutoff_hour:minute` (default 15:30) |
| 2. Circuit breaker | WebSocket disconnected > 30 s |
| 3. Daily loss limit | Realized PnL ≤ −(`equity × max_daily_loss_pct / 100`) |
| 4. Duplicate position | Already holding in the same direction for this symbol |
| 5. Quantity sizing | `floor((equity × risk_pct) / stop_distance)` rounds to 0 |

Gates 2 and 3 are skipped in paper trading / backtesting. The circuit breaker instance comes from `TickRegistry` by reference — no flags or shared state stores.

## ExecRegistry (`exec.py`)

**Input:** `ValidatedOrderEvent`  
**Output:** `None` (terminal stage)

- Idempotency check: if an `Order` row already exists for `signal_id`, the event is dropped silently (prevents double-fills on retry).
- Persists a `PENDING` order row before calling the broker (ensures the order is tracked even if the process crashes mid-call).
- Calls `broker.place_order()` and updates the row to `PLACED`.
- **Paper trading:** simulates an immediate fill from `PriceStore`; updates the order to `FILLED` and adjusts the `Position` row atomically.
- **Live trading:** waits for a postback webhook (Kite order-update callback) to transition the order to `FILLED`.
- Position arithmetic (weighted average price, BUY/SELL qty adjustments) happens inside a `SELECT … FOR UPDATE` transaction to prevent concurrent-fill races.
