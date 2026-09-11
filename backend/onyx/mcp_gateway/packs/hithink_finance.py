"""HiThink / Tonghuashun listed-company finance MCP family.

Six HTTP MCP servers share one ``X-api-key`` (HEADER_MAP). Quotes and
fundamentals change intra-day, so live market tools bypass the cache.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, PackEndpoint, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY, HOUR

HITHINK_BASE = "https://fuyao.aicubes.cn/mcp"

HITHINK_ENDPOINTS: tuple[PackEndpoint, ...] = (
    PackEndpoint(
        slug="hithink-a-share",
        display_name="HiThink A-Share",
        upstream_url=f"{HITHINK_BASE}/a-share",
        description="A-share quotes, financials, and filings.",
    ),
    PackEndpoint(
        slug="hithink-a-share-index",
        display_name="HiThink A-Share Index",
        upstream_url=f"{HITHINK_BASE}/a-share-index",
        description="A-share index constituents and industry context.",
    ),
    PackEndpoint(
        slug="hithink-meta",
        display_name="HiThink Meta",
        upstream_url=f"{HITHINK_BASE}/meta",
        description="Listed-company entity resolution and metadata.",
    ),
    PackEndpoint(
        slug="hithink-fund",
        display_name="HiThink Fund",
        upstream_url=f"{HITHINK_BASE}/fund",
        description="Fund holdings and performance.",
    ),
    PackEndpoint(
        slug="hithink-futures",
        display_name="HiThink Futures",
        upstream_url=f"{HITHINK_BASE}/futures",
        description="Futures contracts and quotes.",
    ),
    PackEndpoint(
        slug="hithink-options",
        display_name="HiThink Options",
        upstream_url=f"{HITHINK_BASE}/options",
        description="Options contracts and quotes.",
    ),
)

HITHINK_ENDPOINT_SLUGS: frozenset[str] = frozenset(
    endpoint.slug for endpoint in HITHINK_ENDPOINTS
)

PACK = ProviderPack(
    slug="hithink-finance",
    display_name="HiThink Finance",
    description="Tonghuashun listed-company quotes, filings, funds, and derivatives.",
    default_upstream_url=f"{HITHINK_BASE}/a-share",
    group="enterprise",
    auth_adapter=MCPGatewayAuthAdapter.HEADER_MAP,
    auth_header_name="X-api-key",
    endpoints=HITHINK_ENDPOINTS,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=HOUR,
        swr_seconds=HOUR,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.BYPASS,
            ttl_seconds=0,
            swr_seconds=0,
            tool_globs=("*quote*", "*tick*", "*realtime*", "*live*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * HOUR,
            swr_seconds=DAY,
            tool_globs=("*financial*", "*filing*", "*report*", "*statement*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("*meta*", "*company*", "*index*"),
        ),
    ),
)
