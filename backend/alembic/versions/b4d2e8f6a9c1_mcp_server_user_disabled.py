"""MCP per-user opt-out table.

Single enable/disable surface for MCP servers (/craft/v1/mcp-actions):
absence of a row means the server is enabled for the user; a row removes an
otherwise-eligible server from that user's sessions.

Revision ID: b4d2e8f6a9c1
Revises: c3f8a9d1e5b2
Create Date: 2026-10-04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b4d2e8f6a9c1"
down_revision = "c3f8a9d1e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_server__user_disabled",
        sa.Column(
            "mcp_server_id",
            sa.Integer(),
            sa.ForeignKey("mcp_server.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("mcp_server__user_disabled")
