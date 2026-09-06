"""mcp personal scope and gateway ops

Fold catalog grants onto mcp_server, migrate SYSTEM rows to USER, add
PERSONAL as a scope value, and add call-log indexes plus a daily stats
rollup so the gateway ops page can page through hundreds of thousands of
calls.

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Catalog group grants become the server's own grants. The product ACL
    # lives on mcp_server after this; catalog groups stay as leftover data.
    op.execute(
        """
        INSERT INTO mcp_server__user_group (mcp_server_id, user_group_id)
        SELECT s.id, g.user_group_id
        FROM mcp_server s
        JOIN mcp_catalog_entry__user_group g
          ON g.catalog_entry_id = s.catalog_entry_id
        WHERE s.catalog_entry_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE mcp_server AS s
        SET is_public = e.is_public
        FROM mcp_catalog_entry AS e
        WHERE s.catalog_entry_id = e.id
          AND s.scope = 'SYSTEM'
        """
    )
    op.execute("UPDATE mcp_server SET scope = 'USER' WHERE scope = 'SYSTEM'")
    # native_enum=False stored the old values as VARCHAR(6) (len("SYSTEM")).
    # PERSONAL is 8 characters.
    op.alter_column(
        "mcp_server",
        "scope",
        existing_type=sa.String(length=6),
        type_=sa.String(length=8),
        existing_nullable=False,
        existing_server_default=sa.text("'USER'"),
    )

    op.add_column(
        "mcp_gateway_call_log",
        sa.Column("arguments_digest", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_mcp_gateway_call_log_created_id",
        "mcp_gateway_call_log",
        ["created_at", "id"],
    )
    op.create_index(
        "ix_mcp_gateway_call_log_catalog_created",
        "mcp_gateway_call_log",
        ["catalog_slug", "created_at"],
    )
    op.create_index(
        "ix_mcp_gateway_call_log_tool_created",
        "mcp_gateway_call_log",
        ["effective_tool_name", "created_at"],
    )
    op.create_index(
        "ix_mcp_gateway_call_log_user_created",
        "mcp_gateway_call_log",
        ["user_email", "created_at"],
    )
    op.create_index(
        "ix_mcp_gateway_call_log_cache_created",
        "mcp_gateway_call_log",
        ["cache_key", "created_at"],
    )

    op.create_table(
        "mcp_gateway_call_stats_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_slug", sa.String(length=128), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("billed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "response_bytes", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "latency_ms_sum", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.UniqueConstraint(
            "catalog_slug",
            "day",
            "outcome",
            name="uq_mcp_gateway_call_stats_daily_slug_day_outcome",
        ),
    )
    op.create_index(
        "ix_mcp_gateway_call_stats_daily_day",
        "mcp_gateway_call_stats_daily",
        ["day"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_gateway_call_stats_daily_day",
        table_name="mcp_gateway_call_stats_daily",
    )
    op.drop_table("mcp_gateway_call_stats_daily")
    op.drop_index(
        "ix_mcp_gateway_call_log_cache_created", table_name="mcp_gateway_call_log"
    )
    op.drop_index(
        "ix_mcp_gateway_call_log_user_created", table_name="mcp_gateway_call_log"
    )
    op.drop_index(
        "ix_mcp_gateway_call_log_tool_created", table_name="mcp_gateway_call_log"
    )
    op.drop_index(
        "ix_mcp_gateway_call_log_catalog_created", table_name="mcp_gateway_call_log"
    )
    op.drop_index(
        "ix_mcp_gateway_call_log_created_id", table_name="mcp_gateway_call_log"
    )
    op.drop_column("mcp_gateway_call_log", "arguments_digest")
    op.alter_column(
        "mcp_server",
        "scope",
        existing_type=sa.String(length=8),
        type_=sa.String(length=6),
        existing_nullable=False,
        existing_server_default=sa.text("'USER'"),
    )
    # Scope and grant copies are not reversed: SYSTEM no longer exists as a
    # product value and re-splitting grants would invent data.
