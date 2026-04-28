from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import polars as pl

from trading.core.schemas import OrderType, Side

_log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Broker]] = {}


class Broker(ABC):
    """
    Abstract base for all broker implementations. Doubles as a self-registering
    plugin registry — same pattern as ``Strategy`` and ``FeatureEngine``.

    Registration
    ------------
    Set a class-level ``alias`` attribute on every concrete subclass:

        class MyBroker(Broker):
            alias = "my_broker"
            ...

    Lookup & instantiation
    ----------------------
        cls  = Broker.get("zerodha")
        inst = Broker.create("zerodha", client=kite_client)
        inst = Broker.create("paper", real_broker=zerodha_instance)

    Note: ``Broker.create()`` passes ``**kwargs`` to the constructor, so each
    broker receives exactly the arguments its ``__init__`` expects.
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
                    f"Duplicate Broker alias {alias!r}: "
                    f"already registered by {existing.__qualname__}, "
                    f"cannot also register {cls.__qualname__}."
                )
        _REGISTRY[alias] = cls
        _log.debug("Broker registered: %r → %s", alias, cls.__qualname__)

    # ── Registry API ──────────────────────────────────────────────────────────

    @classmethod
    def get(cls, alias: str) -> type[Broker]:
        """Return the Broker subclass registered under *alias*."""
        if not _REGISTRY:
            _discover_default()
        try:
            return _REGISTRY[alias]
        except KeyError:
            available = ", ".join(sorted(_REGISTRY))
            raise ValueError(
                f"Unknown Broker alias {alias!r}. "
                f"Available: {available or '(none — run Broker.discover() first)'}."
            ) from None

    @classmethod
    def create(cls, alias: str, **kwargs: Any) -> Broker:
        """Instantiate the broker registered under *alias*, forwarding kwargs."""
        return cls.get(alias)(**kwargs)

    @classmethod
    def registered(cls) -> dict[str, type[Broker]]:
        """Return a snapshot of the alias → class registry."""
        return dict(_REGISTRY)

    @classmethod
    def discover(cls, package: str) -> None:
        """Walk *package* recursively and import every module (idempotent)."""
        _discover(package)

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def get_instruments(self) -> pl.DataFrame:
        pass

    @abstractmethod
    def get_ohlc(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: Side,
        qty: int,
        order_type: OrderType,
        limit_price: float | None = None,
    ) -> str:
        """
        Place an order and return the broker-assigned order ID.

        Parameters
        ----------
        symbol:
            Instrument trading symbol (e.g. "INFY").
        side:
            BUY or SELL.
        qty:
            Number of shares / contracts.
        order_type:
            MARKET, LIMIT, SL, or SL_M.
        limit_price:
            Required for LIMIT and SL orders; None for MARKET/SL_M.

        Returns
        -------
        str
            Broker-assigned order ID (e.g. Zerodha's kite_order_id).
        """
        ...


# ── Discovery helpers ─────────────────────────────────────────────────────────

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
        _log.error("Broker.discover: cannot import package %r — %s", package, exc)
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
            _log.debug("Broker.discover: imported %s", info.name)
        except Exception as exc:
            _log.warning("Broker.discover: failed to import %s — %s", info.name, exc)


_DEFAULT_PACKAGE = "trading.broker"
_default_discovered = False


def _discover_default() -> None:
    global _default_discovered
    if _default_discovered:
        return
    _default_discovered = True
    _discover(_DEFAULT_PACKAGE)
