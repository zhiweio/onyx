"""Tianyancha company intelligence.

Tunnels every call through `call_tool`, so the gateway unwraps the inner tool
name before choosing a policy or building a cache key. Financial reports are
published quarterly, hence the cron refresh rather than a plain TTL.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY, HOUR

PACK = ProviderPack(
    slug="tianyancha",
    display_name="Tianyancha",
    description="Chinese company registry, IP, judicial, and financial data.",
    default_upstream_url="https://mcp.tianyancha.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.RAW_AUTHORIZATION,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=DAY,
    ),
    nested_entry_tools=("call_tool", "call_tools"),
    batch_entry_tools=("call_tools_batch",),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * HOUR,
            swr_seconds=DAY,
            tool_globs=("*risk*", "*lawsuit*", "*judicial*", "*legal*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            schedule_cron="0 4 1 1,4,7,10 *",
            tool_globs=("*finance*", "*financial*", "*report*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("*patent*", "*trademark*", "*ip*", "*copyright*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("companies", "*registration*", "*company*", "*basic*"),
        ),
    ),
)
