"""Qichacha / 企查查 commercial MCP family.

Ten remote stream MCP servers share one Bearer token. History endpoints
need a Qichacha enterprise certificate; they stay registered and optional.
"""

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayRefreshMode
from onyx.mcp_gateway.models import CachePolicySpec, PackEndpoint, ProviderPack
from onyx.mcp_gateway.packs.generic import DAY, HOUR

QCC_BASE = "https://agent.qcc.com/mcp"


def _stream(path: str) -> str:
    return f"{QCC_BASE}/{path}/stream"


# Official paths from https://agent.qcc.com/guide (not /mcp/qcc-*/stream).
QCC_ENDPOINTS: tuple[PackEndpoint, ...] = (
    PackEndpoint(
        slug="qcc-company",
        display_name="Qichacha Company",
        upstream_url=_stream("company"),
        description="Company registry and basic profile.",
    ),
    PackEndpoint(
        slug="qcc-risk",
        display_name="Qichacha Risk",
        upstream_url=_stream("risk"),
        description="Credit, operational, and compliance risk.",
    ),
    PackEndpoint(
        slug="qcc-ipr",
        display_name="Qichacha IPR",
        upstream_url=_stream("ipr"),
        description="Patents, trademarks, and copyrights.",
    ),
    PackEndpoint(
        slug="qcc-operation",
        display_name="Qichacha Operation",
        upstream_url=_stream("operation"),
        description="Operations, bidding, and business changes.",
    ),
    PackEndpoint(
        slug="qcc-history",
        display_name="Qichacha History",
        upstream_url=_stream("history"),
        description="Historical snapshots. Needs a Qichacha enterprise certificate.",
    ),
    PackEndpoint(
        slug="qcc-executive",
        display_name="Qichacha Executive",
        upstream_url=_stream("executive"),
        description="Executives, shareholders, and related parties.",
    ),
    PackEndpoint(
        slug="qcc-legal-regulation",
        display_name="Qichacha Legal Regulation",
        upstream_url=_stream("regulation"),
        description="Administrative penalties and regulatory records.",
    ),
    PackEndpoint(
        slug="qcc-legal-case",
        display_name="Qichacha Legal Case",
        upstream_url=_stream("case"),
        description="Litigation and judgment documents.",
    ),
    PackEndpoint(
        slug="qcc-tender",
        display_name="Qichacha Tender",
        upstream_url=_stream("tender"),
        description="Tenders and bid awards.",
    ),
    PackEndpoint(
        slug="qcc-document",
        display_name="Qichacha Document",
        upstream_url=_stream("document"),
        description="Official filings and attached documents.",
    ),
)

QCC_ENDPOINT_SLUGS: frozenset[str] = frozenset(
    endpoint.slug for endpoint in QCC_ENDPOINTS
)

PACK = ProviderPack(
    slug="qichacha",
    display_name="Qichacha",
    description="Chinese company registry, risk, legal, IP, and tender data.",
    default_upstream_url=_stream("company"),
    group="enterprise",
    auth_adapter=MCPGatewayAuthAdapter.BEARER,
    endpoints=QCC_ENDPOINTS,
    default_policy=CachePolicySpec(
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=DAY,
        swr_seconds=DAY,
    ),
    tool_policies=(
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=12 * HOUR,
            swr_seconds=DAY,
            tool_globs=("*risk*", "*lawsuit*", "*legal*", "*case*", "*penalty*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("*patent*", "*trademark*", "*ipr*", "*copyright*"),
        ),
        CachePolicySpec(
            refresh_mode=MCPGatewayRefreshMode.SWR,
            ttl_seconds=7 * DAY,
            swr_seconds=7 * DAY,
            tool_globs=("*company*", "*registration*", "*basic*", "*executive*"),
        ),
    ),
)
