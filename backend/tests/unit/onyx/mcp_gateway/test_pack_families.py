from types import SimpleNamespace

from onyx.db.enums import MCPGatewayAuthAdapter
from onyx.mcp_gateway.pack_credentials import normalize_pack_credentials
from onyx.server.features.mcp.gateway_bind import apply_pack_upstream_url
from onyx.mcp_gateway.packs.hithink_finance import HITHINK_ENDPOINT_SLUGS, PACK as HITHINK
from onyx.mcp_gateway.packs.qichacha import QCC_ENDPOINT_SLUGS, PACK as QICHACHA
from onyx.mcp_gateway.packs.zhihuiya import PACK as ZHIHUIYA
from onyx.mcp_gateway.packs.zhihuiya_endpoints import (
    ZHIHUIYA_ENDPOINT_SLUGS,
    ZHIHUIYA_EXCLUDED_SLUGS,
    ZHIHUIYA_STARTER,
)
from onyx.mcp_gateway.registry import get_pack


def test_family_packs_are_registered() -> None:
    assert get_pack("hithink-finance").slug == "hithink-finance"
    assert get_pack("qichacha").slug == "qichacha"
    assert get_pack("zhihuiya").slug == "zhihuiya"


def test_hithink_has_six_header_map_endpoints() -> None:
    assert len(HITHINK.resolved_endpoints()) == 6
    assert HITHINK.auth_adapter == MCPGatewayAuthAdapter.HEADER_MAP
    assert HITHINK.auth_header_name == "X-api-key"
    assert "hithink-meta" in HITHINK_ENDPOINT_SLUGS


def test_qichacha_has_ten_bearer_endpoints() -> None:
    assert len(QICHACHA.resolved_endpoints()) == 10
    assert QICHACHA.auth_adapter == MCPGatewayAuthAdapter.BEARER
    assert "qcc-company" in QCC_ENDPOINT_SLUGS
    assert "qcc-history" in QCC_ENDPOINT_SLUGS
    by_slug = {endpoint.slug: endpoint.upstream_url for endpoint in QICHACHA.endpoints}
    assert by_slug["qcc-company"] == "https://agent.qcc.com/mcp/company/stream"
    assert by_slug["qcc-legal-regulation"] == (
        "https://agent.qcc.com/mcp/regulation/stream"
    )
    assert by_slug["qcc-legal-case"] == "https://agent.qcc.com/mcp/case/stream"
    assert QICHACHA.default_upstream_url == by_slug["qcc-company"]


def test_zhihuiya_family_excludes_triz_and_3gpp() -> None:
    slugs = ZHIHUIYA_ENDPOINT_SLUGS
    assert slugs.isdisjoint(ZHIHUIYA_EXCLUDED_SLUGS)
    assert "zhihuiya-core" in slugs
    assert set(ZHIHUIYA_STARTER).issubset(slugs)
    assert "triz" not in slugs
    assert len(ZHIHUIYA.resolved_endpoints()) >= 30


def test_zhihuiya_known_endpoints_use_hex_paths() -> None:
    by_slug = {endpoint.slug: endpoint.upstream_url for endpoint in ZHIHUIYA.endpoints}
    assert by_slug["zhihuiya-core"] == "https://connect.zhihuiya.com/1458a4/mcp"
    assert by_slug["pharma-intelligence"] == (
        "https://connect.zhihuiya.com/096456/logic-mcp"
    )
    assert by_slug["patsnap-search"] == "https://connect.zhihuiya.com/33072f/mcp"
    assert by_slug["patent-status"] == "https://connect.zhihuiya.com/30096b/mcp"
    assert "/mcp/pharma-intelligence" not in by_slug["pharma-intelligence"]


def test_patsnap_pack_uses_zhihuiya_core_url() -> None:
    patsnap = get_pack("patsnap")
    assert patsnap.default_upstream_url == "https://connect.zhihuiya.com/1458a4/mcp"


def test_hithink_header_map_credentials() -> None:
    creds = normalize_pack_credentials(HITHINK, {"api_key": "sk-test"})
    assert creds == {"extra_headers": {"X-api-key": "sk-test"}}
    assert "api_key" not in creds


def test_apply_pack_upstream_url_rewrites_stale_qcc_path() -> None:
    entry = SimpleNamespace(
        slug="qcc-company",
        pack_slug="qichacha",
        upstream_url="https://agent.qcc.com/mcp/qcc-company/stream",
    )
    assert apply_pack_upstream_url(entry) is True
    assert entry.upstream_url == "https://agent.qcc.com/mcp/company/stream"


def test_qichacha_strips_bearer_prefix() -> None:
    creds = normalize_pack_credentials(
        QICHACHA, {"api_key": "Bearer token-value"}
    )
    assert creds["api_key"] == "token-value"
