from dataclasses import dataclass, field
from typing import Any

from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayCallOutcome,
    MCPGatewayRefreshMode,
    MCPTransport,
)


@dataclass(frozen=True)
class CachePolicySpec:
    refresh_mode: MCPGatewayRefreshMode = MCPGatewayRefreshMode.SWR
    ttl_seconds: int = 86400
    swr_seconds: int = 86400
    schedule_cron: str | None = None
    key_fields: list[str] | None = None
    normalize: dict[str, Any] | None = None
    cache_empty_ttl_seconds: int = 3600
    max_response_bytes: int = 2_000_000
    tool_globs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderPack:
    slug: str
    display_name: str
    default_upstream_url: str
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
    auth_adapter: MCPGatewayAuthAdapter = MCPGatewayAuthAdapter.BEARER
    default_policy: CachePolicySpec = field(default_factory=CachePolicySpec)
    tool_policies: tuple[CachePolicySpec, ...] = ()
    nested_entry_tools: tuple[str, ...] = ()
    batch_entry_tools: tuple[str, ...] = ()


@dataclass
class ResolvedCall:
    tool_name: str
    effective_tool_name: str
    arguments: dict[str, Any]
    cache_key: str
    policy: CachePolicySpec
    outcome: MCPGatewayCallOutcome
    result: dict[str, Any]
    upstream_billed: bool
    latency_ms: int
    error_message: str | None = None
