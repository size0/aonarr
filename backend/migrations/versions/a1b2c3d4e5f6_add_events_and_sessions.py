"""add events and production_sessions tables

Track F · Week 2 · Claude-B

Revision ID: a1b2c3d4e5f6
Revises: bd4a112aacb5
Create Date: 2026-05-12 13:30:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "bd4a112aacb5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("book_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", sa.String(length=64), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("parent_event_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_events_book_session_seq",
        "events",
        ["book_id", "session_id", "seq"],
        unique=True,
    )
    op.create_index("idx_events_book_chapter", "events", ["book_id", "chapter_number"])
    op.create_index("idx_events_event_type", "events", ["event_type"])
    op.create_index("idx_events_session_id", "events", ["session_id"])

    op.create_table(
        "production_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("book_id", sa.String(length=64), nullable=False),
        sa.Column("parent_session_id", sa.String(length=64), nullable=True),
        sa.Column("forked_at_event", sa.BigInteger(), nullable=True),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("merged_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_production_sessions_book_id", "production_sessions", ["book_id"])
    op.create_index(
        "idx_prod_session_book_status",
        "production_sessions",
        ["book_id", "status"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_prod_session_book_status", table_name="production_sessions")
    op.drop_index("ix_production_sessions_book_id", table_name="production_sessions")
    op.drop_table("production_sessions")

    op.drop_index("idx_events_session_id", table_name="events")
    op.drop_index("idx_events_event_type", table_name="events")
    op.drop_index("idx_events_book_chapter", table_name="events")
    op.drop_index("idx_events_book_session_seq", table_name="events")
    op.drop_table("events")
