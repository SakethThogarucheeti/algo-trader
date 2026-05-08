# indicators

Technical indicator library with 57+ built-in implementations, an auto-registration system, two pluggable data stores, and an `IndicatorContext` factory for constructing indicators from config.

## Structure

```
indicators/
├── base.py          # Indicator ABC + IndicatorParameters + module-level registry
├── context.py       # IndicatorContext — factory that wires store + symbol + interval
├── store.py         # CandleStore — Postgres + optional Redis (live trading, backtests)
├── polars_store.py  # PolarsStore — in-memory Polars DataFrame (hot path)
└── library/
    ├── adx.py       aroon.py    atr.py      bollinger.py   chaikin.py
    ├── cci.py       cmf.py      cmo.py      dema.py        dpo.py
    ├── ema.py       hull.py     ichimoku.py kama.py        keltner.py
    ├── macd.py      mfi.py      obv.py      psar.py        roc.py
    ├── rsi.py       sma.py      stoch.py    tema.py        trix.py
    ├── tsi.py       uo.py       vwap.py     williams.py    wma.py
    ├── wilder_ema.py   # shared Wilder smoothing helper (α = 1/period)
    └── ...          # 57 total
```

## `Indicator` ABC

```python
class Indicator(ABC):
    alias: str                         # class-level; auto-registers on definition

    def __init__(self, store: CandleStore, symbol: str, interval: str) -> None: ...

    @abstractmethod
    async def compute(self, params: IndicatorParameters) -> float | None: ...

    @classmethod
    def lookup(cls, alias: str) -> type[Indicator]: ...
    @classmethod
    def registered(cls) -> dict[str, type[Indicator]]: ...
```

Auto-registration: setting `alias = "sma"` on a subclass is enough — no factory list to maintain. Duplicate aliases raise `ValueError` at import time.

## `IndicatorParameters`

Frozen Pydantic model base class. Each indicator defines its own `Parameters(IndicatorParameters)` nested class with period, multiplier, and other fields. Passing params per `compute()` call (rather than at construction) allows a single indicator instance to be reused across parameter sweeps.

## Data stores

| Store | Backed by | Best for |
|-------|-----------|----------|
| `PolarsStore` | In-memory Polars DataFrame | Live trading hot path; O(1) append + vectorized compute |
| `CandleStore` | Postgres + optional Redis cache (90 s TTL) | Backtesting; arbitrary lookback without memory constraints |

Strategies use `PolarsStore` during live trading (injected via `AlgoRegistry`). `CandleStore` is used in the backtesting harness and by `IndicatorContext` when instantiating indicators against historical data.

## `IndicatorContext`

Factory class that constructs indicator instances bound to a specific `(store, symbol, interval)`. Used by strategies to avoid constructing indicators manually:

```python
ctx = IndicatorContext(store, symbol, interval)
ema = ctx.get("ema")          # returns EMA(store, symbol, interval)
rsi = ctx.get("rsi")          # returns RSI(store, symbol, interval)
```

## Return value contract

All indicators return `float | None`. `None` means the warmup period has not yet been satisfied (fewer bars available than the indicator requires). Strategies must check for `None` before using a value and return `None` themselves during warmup.

## Adding a new indicator

```python
# indicators/library/my_indicator.py
from trading.indicators.base import Indicator, IndicatorParameters

class MyIndicator(Indicator):
    alias = "my_indicator"

    class Parameters(IndicatorParameters):
        period: int

    async def compute(self, params: Parameters) -> float | None:
        candles = await self._store.fetch(self._symbol, self._interval, limit=params.period)
        if len(candles) < params.period:
            return None
        # … compute and return float
```

No registration call needed — importing the module is sufficient.
