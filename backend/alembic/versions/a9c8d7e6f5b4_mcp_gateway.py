"""mcp gateway provider, cache, and audit tables

Revision ID: a9c8d7e6f5b4
Revises: e8f1a2b3c4d5
Create Date: 2026-08-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a9c8d7e6f5b4"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_server",
        sa.Column(
            "via_gateway",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "mcp_server",
        sa.Column("gateway_provider_slug", sa.String(), nullable=True),
    )

    op.create_table(
        "mcp_gateway_provider",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("pack_slug", sa.String(length=128), nullable=False),
        sa.Column("upstream_url", sa.Text(), nullable=False),
        sa.Column(
            "transport",
            sa.String(),
            nullable=False,
            server_default="STREAMABLE_HTTP",
        ),
        sa.Column(
            "auth_adapter",
            sa.String(),
            nullable=False,
            server_default="bearer",
        ),
        sa.Column("credentials", sa.LargeBinary(), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("tools_list_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_server.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_mcp_gateway_provider_slug"),
    )

    op.create_table(
        "mcp_gateway_cache_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column(
            "refresh_mode",
            sa.String(),
            nullable=False,
            server_default="swr",
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False, server_default="86400"),
        sa.Column("swr_seconds", sa.Integer(), nullable=False, server_default="86400"),
        sa.Column("schedule_cron", sa.String(length=64), nullable=True),
        sa.Column("key_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalize", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "cache_empty_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default="3600",
        ),
        sa.Column(
            "max_response_bytes",
            sa.Integer(),
            nullable=False,
            server_default="2000000",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_slug",
            "tool_name",
            name="uq_mcp_gateway_cache_policy_provider_tool",
        ),
    )
    op.create_index(
        "ix_mcp_gateway_cache_policy_provider",
        "mcp_gateway_cache_policy",
        ["provider_slug"],
    )

    op.create_table(
        "mcp_gateway_cache_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("effective_tool_name", sa.String(length=256), nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "is_empty",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "first_fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_accessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_refresh_status", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "cache_key", name="uq_mcp_gateway_cache_entry_tenant_key"
        ),
    )
    op.create_index(
        "ix_mcp_gateway_cache_entry_provider_tool",
        "mcp_gateway_cache_entry",
        ["provider_slug", "effective_tool_name"],
    )
    op.create_index(
        "ix_mcp_gateway_cache_entry_accessed",
        "mcp_gateway_cache_entry",
        ["last_accessed_at"],
    )

    op.create_table(
        "mcp_gateway_call_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=256), nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("effective_tool_name", sa.String(length=256), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column(
            "upstream_billed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mcp_gateway_call_log_created",
        "mcp_gateway_call_log",
        ["created_at"],
    )
    op.create_index(
        "ix_mcp_gateway_call_log_provider_outcome",
        "mcp_gateway_call_log",
        ["provider_slug", "outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mcp_gateway_call_log_provider_outcome", table_name="mcp_gateway_call_log"
    )
    op.drop_index("ix_mcp_gateway_call_log_created", table_name="mcp_gateway_call_log")
    op.drop_table("mcp_gateway_call_log")
    op.drop_index(
        "ix_mcp_gateway_cache_entry_accessed", table_name="mcp_gateway_cache_entry"
    )
    op.drop_index(
        "ix_mcp_gateway_cache_entry_provider_tool",
        table_name="mcp_gateway_cache_entry",
    )
    op.drop_table("mcp_gateway_cache_entry")
    op.drop_index(
        "ix_mcp_gateway_cache_policy_provider", table_name="mcp_gateway_cache_policy"
    )
    op.drop_table("mcp_gateway_cache_policy")
    op.drop_table("mcp_gateway_provider")
    op.drop_column("mcp_server", "gateway_provider_slug")
    op.drop_column("mcp_server", "via_gateway")
