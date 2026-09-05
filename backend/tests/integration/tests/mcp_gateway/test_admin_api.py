from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser


def test_admin_lists_packs_and_registers_provider(admin_user: DATestUser) -> None:
    packs_response = client.get(
        f"{API_SERVER_URL}/admin/mcp-gateway/packs",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    packs_response.raise_for_status()
    slugs = {item["slug"] for item in packs_response.json()}
    assert {"generic_http", "patsnap", "qixinbao", "tianyancha"} <= slugs

    slug = f"itest-{uuid4().hex[:8]}"
    create_response = client.post(
        f"{API_SERVER_URL}/admin/mcp-gateway/providers",
        json={
            "slug": slug,
            "pack_slug": "generic_http",
            "upstream_url": "http://127.0.0.1:9/mcp",
            "credentials": {"api_key": "test-key"},
            "enabled": True,
            "attach_mcp_server": True,
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    create_response.raise_for_status()
    body = create_response.json()
    assert body["slug"] == slug
    assert body["gateway_url"].endswith(f"/p/{slug}")
    assert body["mcp_server_id"] is not None

    policies_response = client.get(
        f"{API_SERVER_URL}/admin/mcp-gateway/providers/{slug}/policies",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    policies_response.raise_for_status()
    names = {item["tool_name"] for item in policies_response.json()}
    assert "*" in names

    stats_response = client.get(
        f"{API_SERVER_URL}/admin/mcp-gateway/stats",
        params={"provider_slug": slug},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    stats_response.raise_for_status()
    stats = stats_response.json()
    assert stats["total_calls"] == 0

    delete_response = client.delete(
        f"{API_SERVER_URL}/admin/mcp-gateway/providers/{body['id']}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    delete_response.raise_for_status()
