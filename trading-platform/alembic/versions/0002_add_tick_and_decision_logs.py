"""Add tick_logs and decision_logs tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tick_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_token", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("instrument_type", sa.String(), nullable=False),
        sa.Column("last_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tick_logs_instrument_token", "tick_logs", ["instrument_token"])
    op.create_index("ix_tick_logs_symbol", "tick_logs", ["symbol"])
    op.create_index("ix_tick_logs_received_at", "tick_logs", ["received_at"])

    op.create_table(
        "decision_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tick_log_id", sa.Integer(), sa.ForeignKey("tick_logs.id"), nullable=False),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("algo_name", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("signal_id", UUID(as_uuid=True), nullable=True),
        sa.Column("context", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decision_logs_tick_log_id", "decision_logs", ["tick_log_id"])
    op.create_index("ix_decision_logs_step", "decision_logs", ["step"])
    op.create_index("ix_decision_logs_algo_name", "decision_logs", ["algo_name"])
    op.create_index("ix_decision_logs_session_id", "decision_logs", ["session_id"])
    op.create_index("ix_decision_logs_symbol", "decision_logs", ["symbol"])
    op.create_index("ix_decision_logs_created_at", "decision_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("decision_logs")
    op.drop_table("tick_logs")
