"""Cognition DeepWiki for GitHub repositories.

Wiki structure and contents change slowly. `ask_question` is generative —
caching it would return yesterday's answer to a different reader.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode, MCPTransport
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY

PACK = ProviderPack(
    slug="deepwiki",
    display_name="DeepWiki",
    description=(
        "Cognition DeepWiki for public GitHub repos. Use mcp.devin.ai plus a "
        "Bearer token for private repos."
    ),
    default_upstream_url="https://mcp.deepwiki.com/mcp",
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
            swr_seconds=6 * DAY,
            tool_globs=("read_wiki_structure", "read_wiki_contents"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.BYPASS,
            tool_globs=("ask_question",),
        ),
    ),
)
