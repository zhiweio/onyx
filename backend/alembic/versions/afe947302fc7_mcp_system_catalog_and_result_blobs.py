"""mcp system catalog and result blobs

Replaces the first-cut MCP gateway schema with the system/user split:

- `mcp_catalog_entry` holds admin-installed system MCP servers plus their
  shared credentials and cache policy, granted to user groups.
- `mcp_server` gains `scope` and `catalog_entry_id`; the redundant
  `via_gateway` / `gateway_provider_slug` flags go away.
- `mcp_result_blob` stores tool result bodies once, keyed by content hash,
  inline for small payloads and in the file store for large ones.
- The cache entry and call log now point at a blob instead of carrying a JSONB
  body, and the cache entry drops its redundant `tenant_id` column (rows
  already live inside the tenant schema).

The old gateway tables are dropped rather than migrated: they held cache data
that is cheap to refetch, and their shape no longer matches.

Revision ID: afe947302fc7
Revises: f6a7b8c9d0e1
Create Date: 2026-09-05

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "afe947302fc7"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the previous gateway schema. Order matters: the cache policy and
    # cache entry reference the provider by slug, the provider references
    # mcp_server by id.
    op.drop_table("mcp_gateway_call_log")
    op.drop_table("mcp_gateway_cache_entry")
    op.drop_table("mcp_gateway_cache_policy")
    op.drop_table("mcp_gateway_provider")

    op.create_table(
        "mcp_catalog_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("upstream_url", sa.Text(), nullable=False),
        sa.Column(
            "transport",
            sa.Enum(
                "STDIO",
                "SSE",
                "STREAMABLE_HTTP",
                name="mcptransport",
                native_enum=False,
            ),
            server_default="STREAMABLE_HTTP",
            nullable=False,
        ),
        sa.Column(
            "auth_adapter",
            sa.Enum(
                "bearer",
                "raw_authorization",
                "header_map",
                "query_apikey",
                name="mcpgatewayauthadapter",
                native_enum=False,
            ),
            server_default="bearer",
            nullable=False,
        ),
        sa.Column("credentials", sa.LargeBinary(), nullable=False),
        sa.Column("pack_slug", sa.String(length=128), nullable=False),
        sa.Column("policy_overrides", postgresql.JSONB(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "origin",
            sa.Enum("LOCAL", "PUSHED", name="mcpcatalogorigin", native_enum=False),
            server_default="LOCAL",
            nullable=False,
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_mcp_catalog_entry_slug"),
    )
    op.create_index("ix_mcp_catalog_entry_enabled", "mcp_catalog_entry", ["enabled"])

    op.create_table(
        "mcp_catalog_entry__user_group",
        sa.Column("catalog_entry_id", sa.Integer(), nullable=False),
        sa.Column("user_group_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["catalog_entry_id"], ["mcp_catalog_entry.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_group_id"], ["user_group.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("catalog_entry_id", "user_group_id"),
    )

    op.create_table(
        "mcp_result_blob",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "storage",
            sa.Enum("inline", "object", name="mcpresultstorage", native_enum=False),
            nullable=False,
        ),
        sa.Column("inline_payload", postgresql.JSONB(), nullable=True),
        sa.Column("file_id", sa.String(), nullable=True),
        sa.Column("digest", postgresql.JSONB(), nullable=False),
        sa.Column("provider_slug", sa.String(length=128), nullable=True),
        sa.Column("tool_name", sa.String(length=256), nullable=True),
        sa.Column(
            "ref_count", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "created_at",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mcp_result_blob_accessed", "mcp_result_blob", ["last_accessed_at"]
    )

    op.create_table(
        "mcp_gateway_cache_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("catalog_slug", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("effective_tool_name", sa.String(length=256), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("blob_id", sa.String(length=64), nullable=False),
        sa.Column(
            "is_empty", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
        sa.Column(
            "hit_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("last_refresh_status", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["blob_id"], ["mcp_result_blob.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key", name="uq_mcp_gateway_cache_entry_key"),
    )
    op.create_index(
        "ix_mcp_gateway_cache_entry_catalog_tool",
        "mcp_gateway_cache_entry",
        ["catalog_slug", "effective_tool_name"],
    )
    op.create_index(
        "ix_mcp_gateway_cache_entry_accessed",
        "mcp_gateway_cache_entry",
        ["last_accessed_at"],
    )

    op.create_table(
        "mcp_gateway_call_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("catalog_slug", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("effective_tool_name", sa.String(length=256), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "hit",
                "miss",
                "swr",
                "refresh",
                "bypass",
                "error",
                name="mcpgatewaycalloutcome",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "upstream_billed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "response_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result_blob_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["result_blob_id"], ["mcp_result_blob.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mcp_gateway_call_log_created", "mcp_gateway_call_log", ["created_at"]
    )
    op.create_index(
        "ix_mcp_gateway_call_log_catalog_outcome",
        "mcp_gateway_call_log",
        ["catalog_slug", "outcome"],
    )

    op.create_table(
        "mcp_user_enablement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mcp_server_id"], ["mcp_server.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "mcp_server_id", name="uq_mcp_user_enablement_user_server"
        ),
    )

    # mcp_server: scope replaces the via_gateway flag, catalog_entry_id
    # replaces the loose gateway_provider_slug reference.
    op.add_column(
        "mcp_server",
        sa.Column(
            "scope",
            sa.Enum("SYSTEM", "USER", name="mcpserverscope", native_enum=False),
            server_default="USER",
            nullable=False,
        ),
    )
    op.add_column(
        "mcp_server", sa.Column("catalog_entry_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_mcp_server_catalog_entry",
        "mcp_server",
        "mcp_catalog_entry",
        ["catalog_entry_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_mcp_server_scope", "mcp_server", ["scope"])

    # Servers created by the previous gateway are orphaned: their provider row
    # is gone and no catalog entry replaces it. Delete them so they cannot
    # linger as unroutable USER servers pointing at a dead gateway URL.
    op.execute(
        "DELETE FROM mcp_server WHERE via_gateway IS TRUE",
    )
    op.drop_column("mcp_server", "via_gateway")
    op.drop_column("mcp_server", "gateway_provider_slug")


def downgrade() -> None:
    op.add_column(
        "mcp_server", sa.Column("gateway_provider_slug", sa.String(), nullable=True)
    )
    op.add_column(
        "mcp_server",
        sa.Column(
            "via_gateway",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.drop_index("ix_mcp_server_scope", table_name="mcp_server")
    op.drop_constraint("fk_mcp_server_catalog_entry", "mcp_server", type_="foreignkey")
    op.drop_column("mcp_server", "catalog_entry_id")
    op.drop_column("mcp_server", "scope")

    op.drop_table("mcp_user_enablement")
    op.drop_table("mcp_gateway_call_log")
    op.drop_table("mcp_gateway_cache_entry")
    op.drop_table("mcp_result_blob")
    op.drop_table("mcp_catalog_entry__user_group")
    op.drop_table("mcp_catalog_entry")

    op.create_table(
        "mcp_gateway_provider",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("pack_slug", sa.String(length=128), nullable=False),
        sa.Column("upstream_url", sa.Text(), nullable=False),
        sa.Column(
            "transport",
            sa.Enum(
                "STDIO",
                "SSE",
                "STREAMABLE_HTTP",
                name="mcptransport",
                native_enum=False,
            ),
            server_default="STREAMABLE_HTTP",
            nullable=False,
        ),
        sa.Column(
            "auth_adapter",
            sa.Enum(
                "bearer",
                "raw_authorization",
                "header_map",
                "query_apikey",
                name="mcpgatewayauthadapter",
                native_enum=False,
            ),
            server_default="bearer",
            nullable=False,
        ),
        sa.Column("credentials", sa.LargeBinary(), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
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
        sa.ForeignKeyConstraint(
            ["mcp_server_id"], ["mcp_server.id"], ondelete="SET NULL"
        ),
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
            sa.Enum(
                "ttl",
                "swr",
                "schedule",
                "ttl_and_schedule",
                "never",
                "bypass",
                name="mcpgatewayrefreshmode",
                native_enum=False,
            ),
            server_default="swr",
            nullable=False,
        ),
        sa.Column("ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("swr_seconds", sa.Integer(), nullable=False),
        sa.Column("schedule_cron", sa.String(length=64), nullable=True),
        sa.Column("key_fields", postgresql.JSONB(), nullable=True),
        sa.Column("normalize", postgresql.JSONB(), nullable=True),
        sa.Column("cache_empty_ttl_seconds", sa.Integer(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
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
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "is_empty", sa.Boolean(), server_default=sa.text("false"), nullable=False
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
        sa.Column("hit_count", sa.Integer(), nullable=False),
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
        sa.Column(
            "outcome",
            sa.Enum(
                "hit",
                "miss",
                "swr",
                "refresh",
                "bypass",
                "error",
                name="mcpgatewaycalloutcome",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "upstream_billed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
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
        "ix_mcp_gateway_call_log_created", "mcp_gateway_call_log", ["created_at"]
    )
    op.create_index(
        "ix_mcp_gateway_call_log_provider_outcome",
        "mcp_gateway_call_log",
        ["provider_slug", "outcome"],
    )
