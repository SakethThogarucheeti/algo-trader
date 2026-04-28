from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading.config.settings import Settings
from trading.core.clock import Clock
from trading.core.messaging import MessageBus
from trading.risk.base import RiskController
from trading.risk.controller import DefaultRiskController
from trading.storage.base import AbstractRepository


def make_risk_controller(
    rc_id: str,
    *,
    bus: MessageBus,
    repo: AbstractRepository,
    sf: async_sessionmaker[AsyncSession],
    settings: Settings,
    equity: float,
    signals_channel: str,
    validated_orders_channel: str,
    clock: Clock | None = None,
) -> RiskController:
    """Resolve a risk_controller_id string to a RiskController instance.

    To add a new risk controller: add a case here and a class file under
    trading/risk/. No registry dict to maintain.
    """
    match rc_id:
        case "default":
            return DefaultRiskController(
                bus=bus,
                repo=repo,
                session_factory=sf,
                settings=settings,
                equity=equity,
                signals_channel=signals_channel,
                validated_orders_channel=validated_orders_channel,
                clock=clock,
            )
        case _:
            raise ValueError(
                f"Unknown risk_controller_id: {rc_id!r}. "
                f"Add a case to make_risk_controller() in di/providers/risk.py."
            )
