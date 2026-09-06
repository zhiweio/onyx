"""Upstash Context7 library documentation.

Library IDs are stable. Doc queries change when a library ships a release.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode, MCPTransport
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY

PACK = ProviderPack(
    slug="context7",
    display_name="Context7",
    description=(
        "Upstash Context7 library docs. Works without a key; an org Bearer "
        "raises the quota."
    ),
    default_upstream_url="https://mcp.context7.com/mcp",
    group="common",
    transport=MCPTransport.STREAMABLE_HTTP,
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=12 * 3600,
        swr_seconds=12 * 3600,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=6 * DAY,
            tool_globs=("resolve-library-id",),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=DAY,
            tool_globs=("query-docs",),
        ),
    ),
)
