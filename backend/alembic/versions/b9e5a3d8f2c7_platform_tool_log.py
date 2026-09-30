"""platform_tool_log table

Revision ID: b9e5a3d8f2c7
Revises: a8d4f1c7b2e6
Create Date: 2026-09-30

Append-only journal of platform tool calls (tool bridge, MCP gateway,
model probes) backing the audit report page.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b9e5a3d8f2c7"
down_revision = "a8d4f1c7b2e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_tool_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("build_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("result_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_platform_tool_log_user_time", "platform_tool_log", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_platform_tool_log_session_time",
        "platform_tool_log",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("platform_tool_log")
