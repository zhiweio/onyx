"""Craft per-request LLM ledger.

One row per harness assistant message that reported usage, upserted on
(session_id, opencode_message_id) so replayed ``message.updated`` events
never duplicate. Feeds per-session/per-job cost roll-ups and the daily
user_usage totals.

Revision ID: c4e2f8a1b7d3
Revises: a9d3f7c2e6b1
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c4e2f8a1b7d3"
down_revision = "a9d3f7c2e6b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_llm_request",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("opencode_message_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "opencode_message_id",
            name="uq_craft_llm_request_session_message",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["build_session.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_craft_llm_request_session_time",
        "craft_llm_request",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_craft_llm_request_session_time", table_name="craft_llm_request")
    op.drop_table("craft_llm_request")
