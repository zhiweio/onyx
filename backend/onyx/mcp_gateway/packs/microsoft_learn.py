"""Official Microsoft Learn MCP.

Public documentation changes slowly, so search and fetch are safe to cache.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode, MCPTransport
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY

PACK = ProviderPack(
    slug="microsoft_learn",
    display_name="Microsoft Learn",
    description="Official Microsoft Learn MCP. Public docs, no authentication.",
    default_upstream_url="https://learn.microsoft.com/api/mcp",
    group="common",
    transport=MCPTransport.STREAMABLE_HTTP,
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=6 * DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=DAY,
            tool_globs=("microsoft_docs_search", "*search*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=6 * DAY,
            tool_globs=(
                "microsoft_docs_fetch",
                "microsoft_code_sample_search",
                "*fetch*",
            ),
        ),
    ),
)
