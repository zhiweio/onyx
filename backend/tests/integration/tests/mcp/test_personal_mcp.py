"""Personal MCP isolation: only the owner can list or call the server."""

from uuid import uuid4

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

PERSONAL = f"{API_SERVER_URL}/mcp/personal"


def test_personal_mcp_is_owner_isolated(
    admin_user: DATestUser, basic_user: DATestUser
) -> None:
    name = f"personal-{uuid4().hex[:8]}"
    created = client.post(
        f"{PERSONAL}/servers/create",
        json={
            "name": name,
            "server_url": "https://example.com/mcp",
            "auth_type": "NONE",
            "auth_performer": "ADMIN",
            "transport": "STREAMABLE_HTTP",
        },
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    )
    created.raise_for_status()
    server_id = created.json()["server_id"]

    own = client.get(
        f"{PERSONAL}/servers", headers=basic_user.headers, cookies=basic_user.cookies
    )
    own.raise_for_status()
    assert any(item["id"] == server_id for item in own.json()["mcp_servers"])

    other = client.get(
        f"{PERSONAL}/servers", headers=admin_user.headers, cookies=admin_user.cookies
    )
    other.raise_for_status()
    assert all(item["id"] != server_id for item in other.json()["mcp_servers"])

    admin_list = client.get(
        f"{API_SERVER_URL}/admin/mcp/servers",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    admin_list.raise_for_status()
    assert all(item["id"] != server_id for item in admin_list.json()["mcp_servers"])

    hidden = client.get(
        f"{PERSONAL}/servers/{server_id}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    assert hidden.status_code == 404

    client.delete(
        f"{PERSONAL}/server/{server_id}",
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    ).raise_for_status()
