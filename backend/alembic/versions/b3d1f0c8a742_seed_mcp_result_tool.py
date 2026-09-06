"""seed mcp result tool

Adds the built-in tool that reads back an MCP result too large to inline. It is
injected automatically whenever an agent has any MCP tool, so it is not
attached to personas here.

Revision ID: b3d1f0c8a742
Revises: afe947302fc7
Create Date: 2026-09-05

"""

from alembic import op
import sqlalchemy as sa

revision = "b3d1f0c8a742"
down_revision = "afe947302fc7"
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
    existing = conn.execute(
        sa.text(
            "SELECT in_code_tool_id FROM tool WHERE in_code_tool_id = :in_code_tool_id"
        ),
        {"in_code_tool_id": MCP_RESULT_TOOL["in_code_tool_id"]},
    ).fetchone()

    if existing:
        conn.execute(
            sa.text("""
                UPDATE tool
                SET name = :name,
                    display_name = :display_name,
                    description = :description
                WHERE in_code_tool_id = :in_code_tool_id
                """),
            MCP_RESULT_TOOL,
        )
    else:
        conn.execute(
            sa.text("""
                INSERT INTO tool (name, display_name, description, in_code_tool_id, enabled)
                VALUES (:name, :display_name, :description, :in_code_tool_id, :enabled)
                """),
            MCP_RESULT_TOOL,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM tool WHERE in_code_tool_id = :in_code_tool_id"),
        {"in_code_tool_id": MCP_RESULT_TOOL["in_code_tool_id"]},
    )
