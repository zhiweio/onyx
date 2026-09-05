"""Qixinbao company registry and risk data.

Registration records change rarely, risk and litigation records change often,
so they get separate lifetimes.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY, HOUR

PACK = ProviderPack(
    slug="qixinbao",
    display_name="Qixinbao",
    description="Chinese company registry, risk, and litigation lookups.",
    default_upstream_url="https://ai.qixin.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.HEADER_MAP,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * HOUR,
            swr_seconds=12 * HOUR,
            tool_globs=("getAllRiskInfo", "sumLawsuit", "*risk*", "*lawsuit*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("getEnterpriseInfo", "*enterprise*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=3 * DAY,
            swr_seconds=3 * DAY,
            tool_globs=("getAllPersonInfo", "*person*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=DAY,
            swr_seconds=DAY,
            tool_globs=("advSearch", "*search*"),
        ),
    ),
)
