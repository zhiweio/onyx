"""MCP gateway Iceberg prune keys on the cache cursor

Revision ID: f8c9d0e1f2a3
Revises: e7a8b9c0d1e2
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa

revision = "f8c9d0e1f2a3"
down_revision = "e7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_gateway_cache_entry",
        sa.Column("result_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mcp_gateway_cache_entry",
        sa.Column("blob_prefix", sa.String(length=8), nullable=True),
    )
    op.alter_column(
        "mcp_result_blob",
        "storage",
        existing_type=sa.String(length=6),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "mcp_result_blob",
        "storage",
        existing_type=sa.String(length=16),
        type_=sa.String(length=6),
        existing_nullable=False,
    )
    op.drop_column("mcp_gateway_cache_entry", "blob_prefix")
    op.drop_column("mcp_gateway_cache_entry", "result_created_at")
