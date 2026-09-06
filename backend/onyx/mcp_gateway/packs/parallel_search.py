"""Parallel Search MCP.

Live web search must not be reused across users. Page fetch may cache briefly.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode, MCPTransport
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY, HOUR

PACK = ProviderPack(
    slug="parallel_search",
    display_name="Parallel Search",
    description=(
        "Parallel Search MCP. Live web search is not cached; fetch may cache "
        "a page for a short time."
    ),
    default_upstream_url="https://search.parallel.ai/mcp",
    group="common",
    transport=MCPTransport.STREAMABLE_HTTP,
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.BYPASS,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.BYPASS,
            tool_globs=("web_search",),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=HOUR,
            swr_seconds=DAY - HOUR,
            tool_globs=("web_fetch",),
        ),
    ),
)
