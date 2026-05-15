"""Indicator abstract base class and plugin registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from trading.indicators.store import AbstractCandleStore

_log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Indicator]] = {}


class IndicatorParameters(BaseModel):
    """Frozen Pydantic base for all indicator parameter sets."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Indicator(ABC):
    """
    Abstract base for a single technical indicator.

    Subclasses set a class-level ``alias`` to auto-register. Construction takes
    runtime dependencies only (store, symbol, interval, and optionally clock for
    session-aware indicators). Configuration parameters are passed per call via
    ``compute(params)`` — making each compute call stateless and allowing the same
    instance to be reused across symbols or parameter sweeps.

    Each subclass must define a nested ``Parameters(IndicatorParameters)`` class
    and implement ``compute(params)``.
    """

    alias: str  # set on concrete subclasses to register

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        alias = cls.__dict__.get("alias")
        if alias is None:
            return
        if not isinstance(alias, str) or not alias:
            raise TypeError(f"{cls.__name__}.alias must be a non-empty string")
        if alias in _REGISTRY and _REGISTRY[alias] is not cls:
            raise ValueError(
                f"Duplicate Indicator alias {alias!r}: already registered by "
                f"{_REGISTRY[alias].__qualname__}, cannot also register {cls.__qualname__}."
            )
        _REGISTRY[alias] = cls

    def __init__(self, store: AbstractCandleStore, symbol: str, interval: str) -> None:
        self._store = store
        self._symbol = symbol
        self._interval = interval

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def compute(self, params: IndicatorParameters) -> float | None:
        """
        Fetch candles and return the current indicator value.

        Returns None when there are fewer bars than required (warmup not done).
        Implementations must call ``self._store.fetch(...)`` for data.
        Configuration (period, multiplier, etc.) comes from ``params``.
        """

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    @classmethod
    def lookup(cls, alias: str) -> type[Indicator]:
        try:
            return _REGISTRY[alias]
        except KeyError:
            available = ", ".join(sorted(_REGISTRY))
            raise ValueError(
                f"Unknown Indicator alias {alias!r}. Available: {available or '(none)'}."
            ) from None

    @classmethod
    def registered(cls) -> dict[str, type[Indicator]]:
        return dict(_REGISTRY)
