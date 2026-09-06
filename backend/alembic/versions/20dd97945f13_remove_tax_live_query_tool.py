"""remove tax live query tool

The hardcoded Tax live query built-in and its crawlers are gone. Drop the
seeded tool row. persona__tool rows cascade.

Revision ID: 20dd97945f13
Revises: b3d1f0c8a742
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "20dd97945f13"
down_revision = "b3d1f0c8a742"
branch_labels = None
depends_on = None


TAX_LIVE_QUERY_TOOL_ID = "TaxLiveQueryTool"

TAX_LIVE_QUERY_TOOL = {
    "name": "TaxLiveQueryTool",
    "display_name": "Tax live query",
    "description": (
        "Query China tax/official/news sources and commercial MCP plugins "
        "(Qixinbao, PatSnap) at analysis time. Returns cited NormalizedRecords."
    ),
    "in_code_tool_id": TAX_LIVE_QUERY_TOOL_ID,
    "enabled": True,
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": TAX_LIVE_QUERY_TOOL_ID},
    )


def downgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": TAX_LIVE_QUERY_TOOL_ID},
    ).fetchone()
    if existing:
        return
    conn.execute(
        sa.text(
            """
            INSERT INTO tool (name, display_name, description, in_code_tool_id, enabled)
            VALUES (:name, :display_name, :description, :in_code_tool_id, :enabled)
            """
        ),
        TAX_LIVE_QUERY_TOOL,
    )
