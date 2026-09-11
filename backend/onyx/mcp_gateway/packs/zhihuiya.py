"""Zhihuiya / Patsnap patent and life-science MCP family.

Selecting the ``zhihuiya`` skill enables the starter group only. Other
servers stay listed in ``/`` and turn on when the user picks them.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY
from onyx.mcp_gateway.packs.zhihuiya_endpoints import (
    ZHIHUIYA_CORE_URL,
    ZHIHUIYA_ENDPOINTS,
)

PACK = ProviderPack(
    slug="zhihuiya",
    display_name="Zhihuiya",
    description=(
        "Patent, biomed, and company-diligence MCP family. "
        "A /zhihuiya pick enables the starter set only."
    ),
    default_upstream_url=ZHIHUIYA_CORE_URL,
    group="enterprise",
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    endpoints=ZHIHUIYA_ENDPOINTS,
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
            tool_globs=("*eureka*", "*ai_*", "*analyze*", "*draft*", "*report*"),
        ),
    ),
)
