"""remove mcp result tool

The model now receives the original MCP tool result. The follow-up reader
that sliced a stored digest is unused.

Revision ID: d8c2f1a90b47
Revises: 20dd97945f13
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "d8c2f1a90b47"
down_revision = "20dd97945f13"
branch_labels = None
depends_on = None


MCP_RESULT_TOOL = {
    "name": "mcp_result",
    "display_name": "MCP Result Reader",
    "description": (
        "Read part of a large MCP tool result that was stored instead of "
        "returned in full. Pass the result_handle from the tool's digest. "
        "Give a json_path to read one field, or an offset to read the raw "
        "text from that position. Reads are capped, so page through long "
        "text by increasing the offset."
    ),
    "in_code_tool_id": "MCPResultTool",
    "enabled": True,
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": MCP_RESULT_TOOL["in_code_tool_id"]},
    )


def downgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT id FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": MCP_RESULT_TOOL["in_code_tool_id"]},
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
        MCP_RESULT_TOOL,
    )
