"""
Paper trading broker — simulates order execution without hitting Zerodha.

All market data (get_instruments, get_ohlc) is delegated to the real broker
so the strategy sees genuine live data. Only place_order() is faked:

- Returns a PAPER_{uuid} order ID immediately.
- The OrderExecutor detects paper mode and calls handle_fill() at the last
  known price from the shared PriceStore.

PriceStore
----------
A simple mutable dict (symbol → last price) that is updated by KiteIngestor
on every validated tick. The same instance is shared with OrderExecutor so
fills use the most recent traded price.

Usage
-----
Enable by adding  PAPER_TRADING=true  to .env.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import uuid4

import polars as pl

from trading.broker.base.broker import Broker
from trading.core.schemas import OrderType, Side

logger = logging.getLogger(__name__)


class AbstractPriceStore(ABC):
    """
    Read/write interface for the last-known price of each symbol.

    Used by the execution engine to price fills and by the backtester
    to keep the price store current on every bar.
    """

    @abstractmethod
    def update(self, symbol: str, price: float) -> None:
        """Record *price* as the most recent price for *symbol*."""

    @abstractmethod
    def get(self, symbol: str) -> float | None:
        """Return the last known price for *symbol*, or None if not yet seen."""


class PriceStore(AbstractPriceStore):
    """In-memory implementation: symbol → last traded price."""

    def __init__(self) -> None:
        self._prices: dict[str, float] = {}

    def update(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    def get(self, symbol: str) -> float | None:
        return self._prices.get(symbol)


class PaperBroker(Broker):
    """
    Drop-in replacement for ZerodhaBroker in paper trading mode.

    Delegates all read operations to the underlying real broker.
    place_order() logs the simulated order and returns a PAPER_ prefixed ID.
    """

    def __init__(self, real_broker: Broker) -> None:
        self._real = real_broker

    def get_instruments(self) -> pl.DataFrame:
        return self._real.get_instruments()

    def get_ohlc(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        return self._real.get_ohlc(symbol, interval, start, end)

    async def place_order(
        self,
        symbol: str,
        side: Side,
        qty: int,
        order_type: OrderType,
        limit_price: float | None = None,
    ) -> str:
        order_id = f"PAPER_{uuid4().hex[:12].upper()}"
        logger.info(
            "PaperBroker: SIMULATED %s %s x%d %s → %s",
            side.value,
            symbol,
            qty,
            order_type.value,
            order_id,
        )
        return order_id
