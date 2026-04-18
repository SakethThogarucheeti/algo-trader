from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"

    token: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    exchange: Mapped[str] = mapped_column(String)
    instrument_type: Mapped[str] = mapped_column(String)

    # F&O / crypto optional fields — NULL for equity
    underlying: Mapped[str | None] = mapped_column(String, nullable=True)
    expiry: Mapped[date | None] = mapped_column(nullable=True)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(2), nullable=True)  # CE | PE
    lot_size: Mapped[int | None] = mapped_column(nullable=True)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String)
    symbol: Mapped[str] = mapped_column(String)
    instrument_type: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String)
    signal_type: Mapped[str] = mapped_column(String)
    stop_distance: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="signal", cascade="all, delete-orphan"
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    kite_order_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    signal_id: Mapped[UUID] = mapped_column(ForeignKey("signals.id"))
    status: Mapped[str] = mapped_column(String)
    qty: Mapped[int]
    avg_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    signal: Mapped[Signal] = relationship("Signal", back_populates="orders")


class Position(Base):
    __tablename__ = "positions"

    # Composite PK: (INFY, EQUITY) and (INFY, FUTURES) can coexist
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    instrument_type: Mapped[str] = mapped_column(String, primary_key=True)
    net_qty: Mapped[int] = mapped_column(default=0)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    module: Mapped[str] = mapped_column(String, primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    module: Mapped[str] = mapped_column(String)
    level: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TickLog(Base):
    """
    Immutable record of every raw market tick received from the broker WebSocket.

    Every event downstream of a tick (candle, signal, order decision) carries
    the ``id`` of the originating TickLog row, forming a complete causal chain.
    """

    __tablename__ = "tick_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_token: Mapped[int] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    instrument_type: Mapped[str] = mapped_column(String)
    last_price: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    volume: Mapped[int]
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    decisions: Mapped[list[DecisionLog]] = relationship(
        "DecisionLog", back_populates="tick", cascade="all, delete-orphan"
    )


class DecisionLog(Base):
    """
    Audit record for every decision made in response to a tick.

    ``tick_log_id`` links every decision back to its originating tick.
    ``session_id`` identifies a backtest or Monte Carlo run (NULL = live trading).

    Steps:
    - CANDLE_EMITTED     — CandleAggregator closed a bar
    - SIGNAL_GENERATED   — AlgoRunner's strategy produced a signal
    - SIGNAL_ACCEPTED    — RiskController accepted and forwarded the signal
    - SIGNAL_REJECTED    — RiskController rejected the signal (reason in context)
    """

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tick_log_id: Mapped[int] = mapped_column(ForeignKey("tick_logs.id"), index=True)
    step: Mapped[str] = mapped_column(String, index=True)
    algo_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    signal_id: Mapped[UUID | None] = mapped_column(nullable=True)
    context: Mapped[str] = mapped_column(String)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    tick: Mapped[TickLog] = relationship("TickLog", back_populates="decisions")
