"""Craft harness event tape.

Verbatim harness events, captured before translation (see
``SandboxEventEnvelope``): consumers are codex thread replay, cross-runtime
session migration, and audit. Rows prune after the retention window.

Revision ID: d7f4a2c9e1b5
Revises: c4e2f8a1b7d3
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d7f4a2c9e1b5"
down_revision = "c4e2f8a1b7d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "craft_tape_entry",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("subtype", sa.String(length=64), nullable=False),
        sa.Column("runtime", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["build_session.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_craft_tape_session_seq", "craft_tape_entry", ["session_id", "id"]
    )
    op.create_index(
        "ix_craft_tape_session_kind", "craft_tape_entry", ["session_id", "kind"]
    )


def downgrade() -> None:
    op.drop_index("ix_craft_tape_session_kind", table_name="craft_tape_entry")
    op.drop_index("ix_craft_tape_session_seq", table_name="craft_tape_entry")
    op.drop_table("craft_tape_entry")
