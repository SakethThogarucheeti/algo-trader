from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import polars as pl

from trading.core.schemas import InstrumentType, Side, SignalType

_log = logging.getLogger(__name__)

# ── alias → class map populated by __init_subclass__ ──────────────────────────
_REGISTRY: dict[str, type[Strategy]] = {}


@dataclass
class Signal:
    """
    Trading signal produced by a strategy.

    ``stop_distance`` is used by the risk sizer to compute position size
    (e.g. ATR × multiplier). Must be > 0.

    For backtest reproducibility, pass ``timestamp=candle.timestamp`` explicitly
    when constructing a Signal. The default (``datetime.now(UTC)``) is correct
    for live trading but will vary across runs in backtests.

    ``signal_id`` is auto-generated; every call that returns a Signal produces
    a distinct UUID so the execution layer can deduplicate safely.
    """

    symbol: str
    instrument_type: InstrumentType
    side: Side
    strategy_id: str
    signal_type: SignalType
    stop_distance: float  # always > 0

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signal_id: UUID = field(default_factory=uuid4)


class Strategy(ABC):
    """
    Abstract base for all signal generators. Doubles as a self-registering plugin registry.

    Registration
    ------------
    Every concrete subclass that sets a class-level ``alias`` attribute is
    automatically registered when the class is defined:

        class MyStrategy(Strategy):
            alias = "my_strategy"
            ...

    The alias must be unique across the process. Duplicate aliases raise
    ``ValueError`` at class-definition time (import time), so conflicts surface
    immediately rather than at runtime.

    Lookup & instantiation
    ----------------------
        cls  = Strategy.get("my_strategy")       # → MyStrategy class
        inst = Strategy.create("my_strategy")    # → MyStrategy()
        inst = Strategy.create("my_strategy", fast=5, slow=13)

    Discovery
    ---------
    Call ``Strategy.discover("trading.strategy")`` once (or let it happen
    lazily on the first ``Strategy.create()`` call) to walk a package and
    import all modules so their ``__init_subclass__`` hooks fire.

    Dishka integration
    ------------------
    ``Strategy.get(alias)`` returns the class, which can be passed directly to
    ``container.get(cls)`` without any coupling to the container here.

    Contract
    --------
    ``on_candle`` MUST be a pure function — no broker calls, no DB writes,
    no network I/O. Side effects belong in the registry layer.
    """

    # Subclasses set this to register themselves. Abstract subclasses (mixins,
    # intermediate bases) should leave it unset so they are skipped.
    alias: str  # class attribute — not an instance property

    # ── __init_subclass__ auto-registry ───────────────────────────────────────

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        alias = cls.__dict__.get("alias")  # only look at the direct class, not inherited
        if alias is None:
            return
        if not isinstance(alias, str) or not alias:
            raise TypeError(f"{cls.__name__}.alias must be a non-empty string, got {alias!r}")
        if alias in _REGISTRY:
            existing = _REGISTRY[alias]
            if existing is not cls:
                raise ValueError(
                    f"Duplicate strategy alias {alias!r}: "
                    f"already registered by {existing.__qualname__}, "
                    f"cannot also register {cls.__qualname__}."
                )
        _REGISTRY[alias] = cls
        _log.debug("Strategy registered: %r → %s", alias, cls.__qualname__)

    # ── Registry API ──────────────────────────────────────────────────────────

    @classmethod
    def get(cls, alias: str) -> type[Strategy]:
        """
        Return the Strategy subclass registered under *alias*.

        Triggers lazy discovery of the default strategy package on first call
        if the registry is empty.
        """
        if not _REGISTRY:
            _discover_default()
        try:
            return _REGISTRY[alias]
        except KeyError:
            available = ", ".join(sorted(_REGISTRY))
            raise ValueError(
                f"Unknown strategy alias {alias!r}. "
                f"Available: {available or '(none — run Strategy.discover() first)'}."
            ) from None

    @classmethod
    def create(cls, alias: str, **kwargs: Any) -> Strategy:
        """Instantiate the strategy registered under *alias*, forwarding kwargs."""
        return cls.get(alias)(**kwargs)

    @classmethod
    def registered(cls) -> dict[str, type[Strategy]]:
        """Return a snapshot of the alias → class registry (read-only view)."""
        return dict(_REGISTRY)

    @classmethod
    def discover(cls, package: str) -> None:
        """
        Walk *package* recursively and import every module so that subclass
        definitions (and their ``__init_subclass__`` hooks) execute.

        Safe to call multiple times — already-imported modules are skipped.
        """
        _discover(package)

    # ── Instance API ──────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Alias of this strategy instance (delegates to the class attribute)."""
        return self.__class__.alias  # type: ignore[attr-defined]

    def get_state(self) -> dict[str, object]:
        """
        Return a snapshot of live strategy internals for the monitoring dashboard.

        Override to expose strategy-specific values (e.g. current EMA values).
        Merged into ``algo_state.state`` in Postgres after every candle.
        """
        return {}

    @abstractmethod
    def on_candle(
        self,
        symbol: str,
        instrument_type: InstrumentType,
        df: pl.DataFrame,
    ) -> Signal | None:
        """
        Called on every completed candle. Must be a pure function.

        Parameters
        ----------
        symbol:
            Instrument trading symbol (e.g. "INFY").
        instrument_type:
            Equity, futures, options, etc.
        df:
            Rolling OHLCV DataFrame enriched with technical indicators
            (ema_9, ema_21, rsi_14, atr_14, vwap). Call ``df.tail(n)`` as
            needed rather than assuming a fixed length.

        Returns
        -------
        Signal or None
        """


# ── Discovery helpers ─────────────────────────────────────────────────────────

_discovered: set[str] = set()  # packages already walked


def _discover(package: str) -> None:
    """Import all modules under *package* recursively (idempotent)."""
    import importlib
    import pkgutil

    if package in _discovered:
        return
    _discovered.add(package)

    try:
        root = importlib.import_module(package)
    except ImportError as exc:
        _log.error("Strategy.discover: cannot import package %r — %s", package, exc)
        return

    root_path = getattr(root, "__path__", None)
    if root_path is None:
        return  # single-module, not a package

    for info in pkgutil.walk_packages(root_path, prefix=f"{package}."):
        if info.name in _discovered:
            continue
        _discovered.add(info.name)
        try:
            importlib.import_module(info.name)
            _log.debug("Strategy.discover: imported %s", info.name)
        except Exception as exc:
            _log.warning("Strategy.discover: failed to import %s — %s", info.name, exc)


_DEFAULT_PACKAGE = "trading.strategy"
_default_discovered = False


def _discover_default() -> None:
    global _default_discovered
    if _default_discovered:
        return
    _default_discovered = True
    _discover(_DEFAULT_PACKAGE)
