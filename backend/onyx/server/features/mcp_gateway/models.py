from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayRefreshMode,
    MCPTransport,
)


class PackSummary(BaseModel):
    slug: str
    display_name: str
    default_upstream_url: str
    transport: MCPTransport
    auth_adapter: MCPGatewayAuthAdapter


class ProviderCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=128)
    display_name: str | None = None
    pack_slug: str
    upstream_url: str
    transport: MCPTransport | None = None
    auth_adapter: MCPGatewayAuthAdapter | None = None
    credentials: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    attach_mcp_server: bool = True


class ProviderUpdateRequest(BaseModel):
    display_name: str | None = None
    upstream_url: str | None = None
    transport: MCPTransport | None = None
    auth_adapter: MCPGatewayAuthAdapter | None = None
    credentials: dict[str, Any] | None = None
    enabled: bool | None = None


class ProviderResponse(BaseModel):
    id: int
    slug: str
    display_name: str
    pack_slug: str
    upstream_url: str
    transport: MCPTransport
    auth_adapter: MCPGatewayAuthAdapter
    enabled: bool
    mcp_server_id: int | None
    gateway_url: str
    tools_list_refreshed_at: datetime | None
    created_at: datetime


class PolicyUpsertRequest(BaseModel):
    tool_name: str
    refresh_mode: MCPGatewayRefreshMode
    ttl_seconds: int = 86400
    swr_seconds: int = 86400
    schedule_cron: str | None = None
    key_fields: list[str] | None = None
    normalize: dict[str, Any] | None = None
    cache_empty_ttl_seconds: int = 3600
    max_response_bytes: int = 2_000_000


class PolicyResponse(BaseModel):
    tool_name: str
    refresh_mode: MCPGatewayRefreshMode
    ttl_seconds: int
    swr_seconds: int
    schedule_cron: str | None
    key_fields: list[str] | None
    normalize: dict[str, Any] | None
    cache_empty_ttl_seconds: int
    max_response_bytes: int
    is_db_override: bool


class CacheEntryResponse(BaseModel):
    cache_key: str
    provider_slug: str
    tool_name: str
    effective_tool_name: str
    hit_count: int
    last_fetched_at: datetime
    last_accessed_at: datetime
    last_refresh_status: str | None


class InvalidateRequest(BaseModel):
    cache_key: str | None = None
    provider_slug: str | None = None
    tool_name: str | None = None


class RefreshRequest(BaseModel):
    cache_key: str


class StatsResponse(BaseModel):
    total_calls: int
    upstream_billed: int
    cache_hits: int
    hit_rate: float
    saved_calls: int
    by_outcome: dict[str, int]
