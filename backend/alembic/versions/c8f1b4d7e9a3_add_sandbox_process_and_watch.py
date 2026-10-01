"""add sandbox_process and process_watch tables

Revision ID: c8f1b4d7e9a3
Revises: b6f0d3a8e2c5
Create Date: 2026-09-27

Host-side registry for background processes started inside sandboxes via
the agent's `background` tool, plus the watch rows that wake the owning
session when a process's output matches a literal pattern or the process
exits.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8f1b4d7e9a3"
down_revision = "b6f0d3a8e2c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sandbox_process",
        sa.Column("process_id", sa.String(32), primary_key=True),
        sa.Column(
            "sandbox_id",
            sa.UUID(),
            sa.ForeignKey("sandbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("build_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("command_redacted", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="background"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sandbox_process_session", "sandbox_process", ["session_id"])
    op.create_table(
        "process_watch",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "process_id",
            sa.String(32),
            sa.ForeignKey("sandbox_process.process_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.UUID(),
            sa.ForeignKey("build_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pattern", sa.String(256), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_process_watch_process", "process_watch", ["process_id"])


def downgrade() -> None:
    op.drop_index("ix_process_watch_process", table_name="process_watch")
    op.drop_table("process_watch")
    op.drop_index("ix_sandbox_process_session", table_name="sandbox_process")
    op.drop_table("sandbox_process")
