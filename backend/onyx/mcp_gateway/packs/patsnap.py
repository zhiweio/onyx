"""Patsnap / Zhihuiya patent intelligence.

Search results move slowly, patent detail records are effectively immutable
once published, and the AI endpoints are generative — caching those would
return a stale answer to a different question, so they bypass the cache.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY

PACK = ProviderPack(
    slug="patsnap",
    display_name="Patsnap / Zhihuiya",
    description="Patent search, patent detail, and generative research tools.",
    default_upstream_url="https://connect.patsnap.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=DAY,
            tool_globs=("*search*", "*query*", "*literature*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.TTL,
            ttl_seconds=30 * DAY,
            swr_seconds=0,
            tool_globs=("*detail*", "*patent_id*", "*publication*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.BYPASS,
            ttl_seconds=0,
            swr_seconds=0,
            tool_globs=("*eureka*", "*ai_*", "*analyze*", "*draft*"),
        ),
    ),
)
