from fnmatch import fnmatch

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode, MCPTransport
from onyx.mcp_gateway.models import CachePolicySpec, ProviderPack

_DAY = 86400
_HOUR = 3600

GENERIC_HTTP = ProviderPack(
    slug="generic_http",
    display_name="Generic HTTP MCP",
    default_upstream_url="",
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=_DAY,
        swr_seconds=_DAY,
    ),
)

PATSNAP = ProviderPack(
    slug="patsnap",
    display_name="Patsnap / Zhihuiya",
    default_upstream_url="https://connect.patsnap.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=_DAY,
        swr_seconds=_DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=_DAY,
            swr_seconds=_DAY,
            tool_globs=(
                "*search*",
                "*Search*",
                "*query*",
                "*literature*",
            ),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.TTL,
            ttl_seconds=30 * _DAY,
            swr_seconds=0,
            tool_globs=("*detail*", "*patent_id*", "*publication*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.BYPASS,
            ttl_seconds=0,
            swr_seconds=0,
            tool_globs=("*eureka*", "*Eureka*", "*ai_*", "*analyze*", "*draft*"),
        ),
    ),
)

QIXINBAO = ProviderPack(
    slug="qixinbao",
    display_name="Qixinbao",
    default_upstream_url="https://ai.qixin.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.HEADER_MAP,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=_DAY,
        swr_seconds=_DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=_DAY,
            swr_seconds=_DAY,
            tool_globs=("advSearch", "*search*", "*Search*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * _DAY,
            swr_seconds=7 * _DAY,
            tool_globs=("getEnterpriseInfo", "*enterprise*", "*Enterprise*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * _HOUR,
            swr_seconds=12 * _HOUR,
            tool_globs=("getAllRiskInfo", "sumLawsuit", "*risk*", "*lawsuit*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=3 * _DAY,
            swr_seconds=3 * _DAY,
            tool_globs=("getAllPersonInfo", "*person*", "*Person*"),
        ),
    ),
)

TIANYANCHA = ProviderPack(
    slug="tianyancha",
    display_name="Tianyancha",
    default_upstream_url="https://mcp.tianyancha.com/mcp",
    auth_adapter=MCPGatewayAuthAdapter.RAW_AUTHORIZATION,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=_DAY,
        swr_seconds=_DAY,
    ),
    nested_entry_tools=("call_tool", "call_tools"),
    batch_entry_tools=("call_tools_batch",),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * _HOUR,
            swr_seconds=_DAY,
            tool_globs=("*risk*", "*lawsuit*", "*judicial*", "*legal*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * _DAY,
            swr_seconds=7 * _DAY,
            tool_globs=(
                "companies",
                "*registration*",
                "*company*",
                "*basic*",
            ),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * _DAY,
            swr_seconds=7 * _DAY,
            tool_globs=("*patent*", "*trademark*", "*ip*", "*copyright*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
            ttl_seconds=7 * _DAY,
            swr_seconds=7 * _DAY,
            schedule_cron="0 4 1 1,4,7,10 *",
            tool_globs=("*finance*", "*financial*", "*report*"),
        ),
    ),
)

PACKS: dict[str, ProviderPack] = {
    pack.slug: pack
    for pack in (GENERIC_HTTP, PATSNAP, QIXINBAO, TIANYANCHA)
}


def get_pack(slug: str) -> ProviderPack:
    pack = PACKS.get(slug)
    if pack is None:
        return GENERIC_HTTP
    return pack


def list_packs() -> list[ProviderPack]:
    return list(PACKS.values())


def policy_for_tool(pack: ProviderPack, effective_tool_name: str) -> CachePolicySpec:
    lowered = effective_tool_name.lower()
    for spec in pack.tool_policies:
        if any(
            fnmatch(effective_tool_name, glob) or fnmatch(lowered, glob.lower())
            for glob in spec.tool_globs
        ):
            return spec
    return pack.default_policy
