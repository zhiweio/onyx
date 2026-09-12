"""Bind a direct org MCP to the gateway and unbind it back to direct."""

from collections.abc import Generator
from typing import Any
from uuid import uuid4

import pytest

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

ADMIN_MCP = f"{API_SERVER_URL}/admin/mcp"
USER_MCP = f"{API_SERVER_URL}/mcp"
SETTINGS_URL = f"{API_SERVER_URL}/admin/settings"


def _set_module_enabled(user: DATestUser, enabled: bool) -> None:
    response = client.patch(
        SETTINGS_URL,
        json={"mcp_gateway_enabled": enabled},
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()


def _module_enabled(user: DATestUser) -> bool:
    response = client.get(
        f"{API_SERVER_URL}/settings",
        headers=user.headers,
        cookies=user.cookies,
    )
    response.raise_for_status()
    return bool(response.json().get("mcp_gateway_enabled"))


@pytest.fixture
def gateway_enabled(admin_user: DATestUser) -> Generator[None, None, None]:
    previous = _module_enabled(admin_user)
    _set_module_enabled(admin_user, True)
    try:
        yield
    finally:
        _set_module_enabled(admin_user, previous)


UPSTREAM = "http://example.com/mcp"


def _create_direct_org(
    admin_user: DATestUser, *, name: str, is_public: bool = True
) -> dict[str, Any]:
    response = client.post(
        f"{ADMIN_MCP}/server",
        json={
            "name": name,
            "description": "bind/unbind integration",
            "server_url": UPSTREAM,
            "is_public": is_public,
            "groups": [],
            "users": [],
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return response.json()


def _bind(
    admin_user: DATestUser,
    server_id: int,
    *,
    pack_slug: str = "generic_http",
    slug: str | None = None,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = client.patch(
        f"{ADMIN_MCP}/server/{server_id}/gateway-binding",
        json={
            "pack_slug": pack_slug,
            "slug": slug,
            "credentials": credentials or {"api_key": "bind-test-key"},
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return response.json()


def _unbind(admin_user: DATestUser, server_id: int) -> dict[str, Any]:
    response = client.delete(
        f"{ADMIN_MCP}/server/{server_id}/gateway-binding",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return response.json()


def _tool_names(admin_user: DATestUser, server_id: int) -> list[str]:
    response = client.get(
        f"{ADMIN_MCP}/server/{server_id}/db-tools",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return [item["name"] for item in response.json()["tools"]]


def _delete(admin_user: DATestUser, server_id: int) -> None:
    client.delete(
        f"{ADMIN_MCP}/server/{server_id}",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )


def test_bind_then_unbind_keeps_user_listing(
    admin_user: DATestUser,
    basic_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> None:
    name = f"bind-{uuid4().hex[:8]}"
    slug = f"bind-{uuid4().hex[:8]}"
    created = _create_direct_org(admin_user, name=name)
    server_id = created["id"]
    try:
        assert created["gateway_bound"] is False
        assert created["server_url"] == UPSTREAM
        before_tools = _tool_names(admin_user, server_id)

        bound = _bind(admin_user, server_id, slug=slug)
        assert bound["id"] == server_id
        assert bound["name"] == name
        assert bound["gateway_bound"] is True
        assert bound["catalog_slug"] == slug
        assert bound["pack_slug"] == "generic_http"
        assert bound["server_url"].endswith(f"/p/{slug}")
        assert bound["upstream_url"] == UPSTREAM
        assert bound["is_public"] is True
        assert _tool_names(admin_user, server_id) == before_tools

        user_list = client.get(
            f"{USER_MCP}/servers",
            headers=basic_user.headers,
            cookies=basic_user.cookies,
        )
        user_list.raise_for_status()
        visible = [
            item for item in user_list.json()["mcp_servers"] if item["id"] == server_id
        ]
        assert len(visible) == 1
        assert visible[0]["name"] == name
        assert visible[0]["is_public"] is True

        patched = client.patch(
            f"{ADMIN_MCP}/server/{server_id}",
            json={"server_url": "http://example.com/other"},
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )
        patched.raise_for_status()
        assert patched.json()["server_url"].endswith(f"/p/{slug}")
        assert patched.json()["upstream_url"] == "http://example.com/other"

        unbound = _unbind(admin_user, server_id)
        assert unbound["id"] == server_id
        assert unbound["gateway_bound"] is False
        assert unbound["catalog_slug"] is None
        assert unbound["server_url"] == "http://example.com/other"
        assert unbound["upstream_url"] is None
        assert _tool_names(admin_user, server_id) == before_tools

        still_visible = client.get(
            f"{USER_MCP}/servers",
            headers=basic_user.headers,
            cookies=basic_user.cookies,
        )
        still_visible.raise_for_status()
        assert any(
            item["id"] == server_id for item in still_visible.json()["mcp_servers"]
        )
    finally:
        _delete(admin_user, server_id)


def test_update_pack_keeps_slug(
    admin_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> None:
    name = f"repack-{uuid4().hex[:8]}"
    slug = f"repack-{uuid4().hex[:8]}"
    created = _create_direct_org(admin_user, name=name)
    server_id = created["id"]
    try:
        bound = _bind(admin_user, server_id, slug=slug)
        gateway_url = bound["server_url"]
        updated = _bind(admin_user, server_id, pack_slug="deepwiki")
        assert updated["catalog_slug"] == slug
        assert updated["pack_slug"] == "deepwiki"
        assert updated["server_url"] == gateway_url
    finally:
        _delete(admin_user, server_id)


def test_personal_mcp_cannot_bind(
    admin_user: DATestUser,
    basic_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> None:
    created = client.post(
        f"{API_SERVER_URL}/mcp/personal/servers/create",
        json={
            "name": f"personal-bind-{uuid4().hex[:8]}",
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
    try:
        response = client.patch(
            f"{ADMIN_MCP}/server/{server_id}/gateway-binding",
            json={"pack_slug": "generic_http"},
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )
        assert response.status_code in (403, 404)
    finally:
        client.delete(
            f"{API_SERVER_URL}/mcp/personal/server/{server_id}",
            headers=basic_user.headers,
            cookies=basic_user.cookies,
        )
