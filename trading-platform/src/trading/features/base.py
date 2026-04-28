from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import polars as pl

from trading.core.schemas import CandleEvent

_log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[FeatureEngine]] = {}


class FeatureEngine(ABC):
    """
    Abstract base for per-(symbol, interval) feature computation. Doubles as a
    self-registering plugin registry — same pattern as ``Strategy``.

    Registration
    ------------
    Set a class-level ``alias`` attribute on every concrete subclass:

        class MyEngine(FeatureEngine):
            alias = "my_engine"
            ...

    The subclass auto-registers itself at class-definition time. Duplicate
    aliases raise ``ValueError`` immediately (import time).

    Lookup & instantiation
    ----------------------
        cls  = FeatureEngine.get("technical")
        inst = FeatureEngine.create("technical")
        inst = FeatureEngine.create("technical", ema_spans=(5, 13))

    Discovery
    ---------
    ``FeatureEngine.discover("trading.features")`` walks the package and imports
    all modules. Called lazily on the first ``FeatureEngine.create()`` call.

    Contract
    --------
    ``update`` and ``get`` must be pure with respect to external I/O — no broker
    calls, no DB writes. Feature computation only.
    """

    alias: str  # class attribute — set on concrete subclasses to register

    # ── __init_subclass__ auto-registry ───────────────────────────────────────

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        alias = cls.__dict__.get("alias")
        if alias is None:
            return
        if not isinstance(alias, str) or not alias:
            raise TypeError(f"{cls.__name__}.alias must be a non-empty string, got {alias!r}")
        if alias in _REGISTRY:
            existing = _REGISTRY[alias]
            if existing is not cls:
                raise ValueError(
                    f"Duplicate FeatureEngine alias {alias!r}: "
                    f"already registered by {existing.__qualname__}, "
                    f"cannot also register {cls.__qualname__}."
                )
        _REGISTRY[alias] = cls
        _log.debug("FeatureEngine registered: %r → %s", alias, cls.__qualname__)

    # ── Registry API ──────────────────────────────────────────────────────────

    @classmethod
    def lookup(cls, alias: str) -> type[FeatureEngine]:
        """Return the FeatureEngine subclass registered under *alias*."""
        if not _REGISTRY:
            _discover_default()
        try:
            return _REGISTRY[alias]
        except KeyError:
            available = ", ".join(sorted(_REGISTRY))
            raise ValueError(
                f"Unknown FeatureEngine alias {alias!r}. "
                f"Available: {available or '(none — run FeatureEngine.discover() first)'}."
            ) from None

    @classmethod
    def create(cls, alias: str, **kwargs: Any) -> FeatureEngine:
        """Instantiate the feature engine registered under *alias*."""
        return cls.lookup(alias)(**kwargs)

    @classmethod
    def registered(cls) -> dict[str, type[FeatureEngine]]:
        """Return a snapshot of the alias → class registry."""
        return dict(_REGISTRY)

    @classmethod
    def discover(cls, package: str) -> None:
        """Walk *package* recursively and import every module (idempotent)."""
        _discover(package)

    # ── Instance API ──────────────────────────────────────────────────────────

    @property
    def id(self) -> str:
        """Alias of this engine instance (delegates to the class attribute)."""
        return self.__class__.alias  # type: ignore[attr-defined]

    @abstractmethod
    def update(self, event: CandleEvent) -> pl.DataFrame:
        """
        Append *event* to the rolling window and recompute all indicators.

        Returns the full updated DataFrame including OHLCV and all computed
        indicator columns. The strategy should call ``.tail(n)`` as needed.
        """

    @abstractmethod
    def get(self, symbol: str, interval: str) -> pl.DataFrame | None:
        """
        Return the current DataFrame for *(symbol, interval)* without updating.

        Returns ``None`` if no data has been ingested yet for this pair.
        """


# ── Discovery helpers (identical structure to strategy/base.py) ───────────────

_discovered: set[str] = set()


def _discover(package: str) -> None:
    import importlib
    import pkgutil

    if package in _discovered:
        return
    _discovered.add(package)

    try:
        root = importlib.import_module(package)
    except ImportError as exc:
        _log.error("FeatureEngine.discover: cannot import package %r — %s", package, exc)
        return

    root_path = getattr(root, "__path__", None)
    if root_path is None:
        return

    for info in pkgutil.walk_packages(root_path, prefix=f"{package}."):
        if info.name in _discovered:
            continue
        _discovered.add(info.name)
        try:
            importlib.import_module(info.name)
            _log.debug("FeatureEngine.discover: imported %s", info.name)
        except Exception as exc:
            _log.warning("FeatureEngine.discover: failed to import %s — %s", info.name, exc)


_DEFAULT_PACKAGE = "trading.features"
_default_discovered = False


def _discover_default() -> None:
    global _default_discovered
    if _default_discovered:
        return
    _default_discovered = True
    _discover(_DEFAULT_PACKAGE)
