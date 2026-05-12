"""add book_states table

Track F · Week 3 · Claude-C

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-12 14:10:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "book_states",
        sa.Column("book_id", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("current_chapter", sa.Integer(), nullable=False),
        sa.Column("target_chapter_count", sa.Integer(), nullable=False),
        sa.Column("daemon_status", sa.String(length=32), nullable=False),
        sa.Column("daemon_pid", sa.Integer(), nullable=True),
        sa.Column("daemon_host", sa.String(length=128), nullable=True),
        sa.Column("llm_quota_used", sa.Integer(), nullable=False),
        sa.Column("llm_quota_max", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("last_message", sa.String(length=512), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("book_id"),
    )
    op.create_index("idx_book_states_phase", "book_states", ["phase"])
    op.create_index("idx_book_states_daemon_status", "book_states", ["daemon_status"])


def downgrade() -> None:
    op.drop_index("idx_book_states_daemon_status", table_name="book_states")
    op.drop_index("idx_book_states_phase", table_name="book_states")
    op.drop_table("book_states")
