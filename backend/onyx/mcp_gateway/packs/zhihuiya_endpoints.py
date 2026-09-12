"""Zhihuiya / Patsnap marketplace endpoints that we register as built-in.

URLs omit ``?apikey=``. Auth is Bearer on the catalog entry.

Do not register TRIZ, 3GPP/TDoc, or the IP course center. Workspace and
document-processing stay optional later.
"""

from onyx.mcp_gateway.models import PackEndpoint

ZHIHUIYA_CONNECT = "https://connect.zhihuiya.com"


def _hex(hex_id: str, *, logic: bool = False) -> str:
    suffix = "logic-mcp" if logic else "mcp"
    return f"{ZHIHUIYA_CONNECT}/{hex_id}/{suffix}"


# Featured patent MCP (also the updated Patsnap pack URL).
ZHIHUIYA_CORE_URL = _hex("1458a4")

ZHIHUIYA_ENDPOINTS: tuple[PackEndpoint, ...] = (
    PackEndpoint(
        slug="zhihuiya-core",
        display_name="Zhihuiya Core",
        upstream_url=ZHIHUIYA_CORE_URL,
        description="Featured patent search and detail MCP.",
    ),
    PackEndpoint(
        slug="pharma-intelligence",
        display_name="Pharma Intelligence",
        upstream_url=_hex("096456", logic=True),
        description="Drug, pipeline, and indication intelligence.",
    ),
    PackEndpoint(
        slug="target-disease",
        display_name="Target Disease",
        upstream_url=_hex("2a2645", logic=True),
        description="Target and disease landscape.",
    ),
    PackEndpoint(
        slug="drug-asset",
        display_name="Drug Asset",
        upstream_url=_hex("30cd71", logic=True),
        description="Drug asset and molecule records.",
    ),
    PackEndpoint(
        slug="biology-modality",
        display_name="Biology Modality",
        upstream_url=_hex("06e741", logic=True),
        description="Modality and biology classification.",
    ),
    PackEndpoint(
        slug="chemical-molecular",
        display_name="Chemical Molecular",
        upstream_url=_hex("713886", logic=True),
        description="Chemical structure and molecular data.",
    ),
    PackEndpoint(
        slug="sar-extraction",
        display_name="SAR Extraction",
        upstream_url=_hex("c8ffec", logic=True),
        description="Structure-activity relationship extraction.",
    ),
    PackEndpoint(
        slug="scientific-translational-evidence",
        display_name="Scientific Translational Evidence",
        upstream_url=_hex("9c333c", logic=True),
        description="Translational evidence from literature.",
    ),
    PackEndpoint(
        slug="regulatory-guidelines",
        display_name="Regulatory Guidelines",
        upstream_url=_hex("6415c2", logic=True),
        description="Regulatory guidance documents.",
    ),
    PackEndpoint(
        slug="current-awareness",
        display_name="Current Awareness",
        upstream_url=_hex("401c6d", logic=True),
        description="Current awareness alerts.",
    ),
    PackEndpoint(
        slug="literature-search",
        display_name="Literature Search",
        upstream_url=_hex("eba075"),
        description="Scientific literature search.",
    ),
    PackEndpoint(
        slug="company-deal-intelligence",
        display_name="Company Deal Intelligence",
        upstream_url=_hex("1f8934", logic=True),
        description="Licensing and deal intelligence.",
    ),
    PackEndpoint(
        slug="patsnap-search",
        display_name="Patsnap Search",
        upstream_url=_hex("33072f"),
        description="Patent search (offset + limit cap 1000).",
    ),
    PackEndpoint(
        slug="patent-briefing",
        display_name="Patent Briefing",
        upstream_url=_hex("958a46"),
        description="Patent briefing and preferred detail backend.",
    ),
    PackEndpoint(
        slug="patent-dispute",
        display_name="Patent Dispute",
        upstream_url=_hex("4f9217"),
        description="Patent litigation and disputes.",
    ),
    PackEndpoint(
        slug="patent-monetize",
        display_name="Patent Monetize",
        upstream_url=_hex("11227f"),
        description="Patent monetization signals.",
    ),
    PackEndpoint(
        slug="patent-fto",
        display_name="Patent FTO",
        upstream_url=_hex("e5851d"),
        description="Freedom-to-operate analysis.",
    ),
    PackEndpoint(
        slug="patent-connector",
        display_name="Patent Connector",
        upstream_url=_hex("cac75e"),
        description="Patent family and citation links.",
    ),
    PackEndpoint(
        slug="patent-status",
        display_name="Patent Status",
        upstream_url=_hex("30096b"),
        description="Legal status and events.",
    ),
    PackEndpoint(
        slug="patent-analysis",
        display_name="Patent Analysis",
        upstream_url=_hex("e14e5f", logic=True),
        description="Patent analysis and clustering.",
    ),
    PackEndpoint(
        slug="patent-landscape",
        display_name="Patent Landscape",
        upstream_url=_hex("59100a"),
        description="Landscape views (page cap 20000).",
    ),
    PackEndpoint(
        slug="patent-visual",
        display_name="Patent Visual",
        upstream_url=_hex("3fd502"),
        description="Patent visualization.",
    ),
    PackEndpoint(
        slug="patent-value",
        display_name="Patent Value",
        upstream_url=_hex("67d1b4"),
        description="Patent value scores.",
    ),
    PackEndpoint(
        slug="patsnap-analytics",
        display_name="Patsnap Analytics",
        upstream_url=_hex("2ff4d4", logic=True),
        description="Analytics aggregations.",
    ),
    PackEndpoint(
        slug="patsnap-ip-searching",
        display_name="Patsnap IP Searching",
        upstream_url=_hex("f176d7"),
        description="Novelty and IP search workflow.",
    ),
    PackEndpoint(
        slug="novelty-search-lite",
        display_name="Novelty Search Lite",
        upstream_url=_hex("299425"),
        description="Lite novelty search.",
    ),
    PackEndpoint(
        slug="report-gen",
        display_name="Report Gen",
        upstream_url=_hex("1fadfc"),
        description="Generated patent reports.",
    ),
    PackEndpoint(
        slug="design-fto-search-mcp",
        display_name="Design FTO Search",
        upstream_url=_hex("937ec6"),
        description="Design-patent FTO. Quota-gated.",
    ),
    PackEndpoint(
        slug="company-credit",
        display_name="Company Credit",
        upstream_url=_hex("ed1a0d"),
        description="Company credit and diligence starter.",
    ),
    PackEndpoint(
        slug="company-profile",
        display_name="Company Profile",
        upstream_url=_hex("e7d2b1"),
        description="Company profile.",
    ),
    PackEndpoint(
        slug="company-risk",
        display_name="Company Risk",
        upstream_url=_hex("624fc7"),
        description="Company risk signals.",
    ),
    PackEndpoint(
        slug="company-tags",
        display_name="Company Tags",
        upstream_url=_hex("3cfbf5"),
        description="Company technology tags.",
    ),
    PackEndpoint(
        slug="global-tech-eval",
        display_name="Global Tech Eval",
        upstream_url=_hex("ac58e5"),
        description="Global technology evaluation.",
    ),
    PackEndpoint(
        slug="tech-diligence",
        display_name="Tech Diligence",
        upstream_url=_hex("3faf81"),
        description="Technology due diligence.",
    ),
    PackEndpoint(
        slug="tech-collab",
        display_name="Tech Collab",
        upstream_url=_hex("81cc1c"),
        description="Collaboration and partner search.",
    ),
    PackEndpoint(
        slug="patent-risk",
        display_name="Patent Risk",
        upstream_url=_hex("a8a128"),
        description="Patent risk scoring.",
    ),
)

ZHIHUIYA_ENDPOINT_SLUGS: frozenset[str] = frozenset(
    endpoint.slug for endpoint in ZHIHUIYA_ENDPOINTS
)

ZHIHUIYA_EXCLUDED_SLUGS: frozenset[str] = frozenset(
    {
        "triz",
        "3gpp",
        "tdoc",
        "ip-course-center",
        "patsnap-workspace",
        "document-processing",
    }
)

ZHIHUIYA_STARTER: tuple[str, ...] = (
    "pharma-intelligence",
    "patsnap-search",
    "biology-modality",
    "patent-analysis",
    "patent-briefing",
    "company-credit",
)

ZHIHUIYA_PATENT: tuple[str, ...] = (
    "patsnap-search",
    "patent-briefing",
    "patsnap-analytics",
    "patent-landscape",
    "patent-analysis",
    "patent-value",
    "patent-status",
)

ZHIHUIYA_BIOMED: tuple[str, ...] = (
    "pharma-intelligence",
    "target-disease",
    "biology-modality",
    "literature-search",
    "drug-asset",
    "chemical-molecular",
)

ZHIHUIYA_COMPANY: tuple[str, ...] = (
    "company-credit",
    "company-profile",
    "company-risk",
    "tech-diligence",
    "company-tags",
)

ZHIHUIYA_MCP_GROUPS: dict[str, list[str]] = {
    "zhihuiya-starter": list(ZHIHUIYA_STARTER),
    "zhihuiya-patent": list(ZHIHUIYA_PATENT),
    "zhihuiya-biomed": list(ZHIHUIYA_BIOMED),
    "zhihuiya-company": list(ZHIHUIYA_COMPANY),
}
