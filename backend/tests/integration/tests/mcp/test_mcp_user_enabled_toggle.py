"""Integration tests for the per-user MCP enable/disable surface.

`PATCH /mcp/server/{id}/enabled` is the single toggle behind
/craft/v1/mcp-actions. It must work for admin-built-in (org) servers, affect
only the calling user's domain, and never change server-global config.
"""

from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPTransport,
)
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user import UserManager
from tests.integration.common_utils.test_models import DATestUser

# No live MCP server is contacted: listings and the toggle never dial the URL.
MCP_SERVER_URL = "https://mcp.invalid/org"


def _create_org_server(
    admin_user: DATestUser, name: str, *, is_public: bool, craft: bool
) -> int:
    response = client.post(
        f"{API_SERVER_URL}/admin/mcp/servers/create",
        json={
            "name": name,
            "server_url": MCP_SERVER_URL,
            "transport": MCPTransport.STREAMABLE_HTTP.value,
            "auth_type": MCPAuthenticationType.NONE.value,
            "auth_performer": MCPAuthenticationPerformer.ADMIN.value,
            "is_public": is_public,
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    server_id = response.json()["server_id"]
    if craft:
        toggle = client.patch(
            f"{API_SERVER_URL}/admin/mcp/server/{server_id}",
            json={"available_in_craft": True},
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )
        toggle.raise_for_status()
    return server_id


def _delete_server(admin_user: DATestUser, server_id: int) -> None:
    response = client.delete(
        f"{API_SERVER_URL}/admin/mcp/server/{server_id}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()


def _get_servers(user: DATestUser, path: str) -> list[dict]:
    response = client.get(
        f"{API_SERVER_URL}{path}",
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    return response.json()["mcp_servers"]


def _set_enabled(user: DATestUser, server_id: int, enabled: bool) -> None:
    response = client.patch(
        f"{API_SERVER_URL}/mcp/server/{server_id}/enabled",
        json={"enabled": enabled},
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()


def test_org_server_toggle_is_per_user(
    admin_user: DATestUser,
    basic_user: DATestUser,
) -> None:
    server_id = _create_org_server(
        admin_user, "user-enabled-toggle", is_public=True, craft=True
    )
    try:
        _run_toggle_assertions(admin_user, basic_user, server_id)
    finally:
        _delete_server(admin_user, server_id)


def _run_toggle_assertions(
    admin_user: DATestUser,  # noqa: ARG001
    basic_user: DATestUser,
    server_id: int,
) -> None:

    # Default is enabled everywhere the server is visible.
    gallery = _get_servers(basic_user, "/mcp/servers/gallery")
    entry = next(s for s in gallery if s["id"] == server_id)
    assert entry["user_enabled"] is True
    craft = _get_servers(basic_user, "/mcp/servers/craft")
    assert server_id in [s["id"] for s in craft]

    # The calling user opts out: their injection set drops the server...
    _set_enabled(basic_user, server_id, False)
    gallery = _get_servers(basic_user, "/mcp/servers/gallery")
    entry = next(s for s in gallery if s["id"] == server_id)
    assert entry["user_enabled"] is False
    craft = _get_servers(basic_user, "/mcp/servers/craft")
    assert server_id not in [s["id"] for s in craft]

    # ...while another user's domain and the server-global config are intact.
    other_user = UserManager.create()
    other_gallery = _get_servers(other_user, "/mcp/servers/gallery")
    other_entry = next(s for s in other_gallery if s["id"] == server_id)
    assert other_entry["user_enabled"] is True
    assert other_entry["available_in_craft"] is True
    other_craft = _get_servers(other_user, "/mcp/servers/craft")
    assert server_id in [s["id"] for s in other_craft]

    # Opting back in restores the server for the calling user only.
    _set_enabled(basic_user, server_id, True)
    craft = _get_servers(basic_user, "/mcp/servers/craft")
    assert server_id in [s["id"] for s in craft]


def test_toggle_requires_access_to_the_server(
    admin_user: DATestUser,
    basic_user: DATestUser,
) -> None:
    server_id = _create_org_server(
        admin_user, "user-enabled-private", is_public=False, craft=False
    )
    try:
        response = client.patch(
            f"{API_SERVER_URL}/mcp/server/{server_id}/enabled",
            json={"enabled": False},
            headers=basic_user.headers,
            cookies=basic_user.cookies,
        )
        assert response.status_code == 404
    finally:
        _delete_server(admin_user, server_id)
