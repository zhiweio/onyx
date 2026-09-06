from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from onyx.db.enums import (
    MCPCatalogOrigin,
    MCPGatewayAuthAdapter,
    MCPGatewayRefreshMode,
    MCPTransport,
)
from onyx.server.features.mcp_catalog.slug import catalog_slug_from_input


class PackSummary(BaseModel):
    slug: str
    display_name: str
    description: str
    default_upstream_url: str
    transport: MCPTransport
    auth_adapter: MCPGatewayAuthAdapter


class CatalogEntryCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=256)
    display_name: str | None = None
    description: str | None = None
    pack_slug: str
    upstream_url: str
    transport: MCPTransport | None = None
    auth_adapter: MCPGatewayAuthAdapter | None = None
    credentials: dict[str, Any] = Field(default_factory=dict)
    policy_overrides: dict[str, Any] | None = None
    enabled: bool = True
    is_public: bool = False
    group_ids: list[int] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        # Accept a package name such as "@upstash/context7-mcp" and store the
        # catalog form "upstash-context7-mcp".
        return catalog_slug_from_input(value)


class CatalogEntryUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    pack_slug: str | None = None
    upstream_url: str | None = None
    transport: MCPTransport | None = None
    auth_adapter: MCPGatewayAuthAdapter | None = None
    credentials: dict[str, Any] | None = None
    policy_overrides: dict[str, Any] | None = None
    enabled: bool | None = None
    is_public: bool | None = None
    group_ids: list[int] | None = None


class CatalogEntryResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    description: str | None
    pack_slug: str
    upstream_url: str
    transport: MCPTransport
    auth_adapter: MCPGatewayAuthAdapter
    enabled: bool
    is_public: bool
    origin: MCPCatalogOrigin
    group_ids: list[int]
    mcp_server_id: int | None
    gateway_url: str
    tool_count: int
    tools_list_refreshed_at: datetime | None
    created_at: datetime
    # True when the entry holds upstream credentials. The values themselves are
    # never returned.
    has_credentials: bool
    # Set when install or refresh could not read the upstream tool list. The
    # entry is still saved so the admin can fix the URL or key and retry.
    discovery_error: str | None = None


class SystemMCPServerResponse(BaseModel):
    """One system MCP server as a user sees it on the settings page."""

    mcp_server_id: int
    catalog_slug: str
    display_name: str
    description: str | None
    enabled_for_user: bool
    tool_count: int


class SetEnablementRequest(BaseModel):
    enabled: bool


class PolicyResponse(BaseModel):
    label: str
    refresh_mode: MCPGatewayRefreshMode
    ttl_seconds: int
    swr_seconds: int
    schedule_cron: str | None
    key_fields: list[str] | None
    cache_empty_ttl_seconds: int
    inline_threshold_bytes: int
    max_response_bytes: int
    digest_max_bytes: int
    is_override: bool


class CacheEntryResponse(BaseModel):
    cache_key: str
    catalog_slug: str
    tool_name: str
    effective_tool_name: str
    hit_count: int
    size_bytes: int
    storage: str
    last_fetched_at: datetime
    last_accessed_at: datetime
    last_refresh_status: str | None


class InvalidateRequest(BaseModel):
    cache_key: str | None = None
    catalog_slug: str | None = None
    tool_name: str | None = None


class RefreshRequest(BaseModel):
    cache_key: str


class StatsResponse(BaseModel):
    total_calls: int
    upstream_billed: int
    cache_hits: int
    hit_rate: float
    saved_calls: int
    total_response_bytes: int
    by_outcome: dict[str, int]
    blob_total_count: int
    blob_total_bytes: int
    blob_by_storage: dict[str, dict[str, int]]
    retention_days: int = 30
    top_servers: list[dict[str, Any]] = Field(default_factory=list)
    top_tools: list[dict[str, Any]] = Field(default_factory=list)


class CacheListResponse(BaseModel):
    items: list[CacheEntryResponse]
    next_cursor: str | None = None
    total: int = 0


class CallLogListItem(BaseModel):
    id: int
    created_at: datetime
    catalog_slug: str
    tool_name: str
    effective_tool_name: str
    outcome: str
    upstream_billed: bool
    latency_ms: int
    response_bytes: int
    user_email: str | None
    session_id: str | None
    cache_key: str
    arguments_preview: str
    error_message: str | None = None


class CallLogListResponse(BaseModel):
    items: list[CallLogListItem]
    next_cursor: str | None = None


class CallLogDetailResponse(CallLogListItem):
    arguments: dict[str, Any] = Field(default_factory=dict)
