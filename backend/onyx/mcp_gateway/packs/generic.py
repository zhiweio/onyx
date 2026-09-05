"""Fallback pack for any MCP server the gateway does not know.

Conservative defaults: cache for a day, serve stale for a day while
refreshing. An admin tunes the rest per catalog entry.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack

DAY = 86400
HOUR = 3600

PACK = ProviderPack(
    slug="generic_http",
    display_name="Generic HTTP MCP",
    description="Any MCP server reachable over Streamable HTTP or SSE.",
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=DAY,
    ),
)
