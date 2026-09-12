"""Organization MCP + gateway binding, checked against a real deployment."""

from collections.abc import Generator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user_group import UserGroupManager
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


@pytest.fixture
def installed_server(
    admin_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> Generator[dict[str, Any], None, None]:
    slug = f"itest-{uuid4().hex[:8]}"
    response = client.post(
        f"{ADMIN_MCP}/servers/from-pack",
        json={
            "pack_slug": "generic_http",
            "name": slug,
            "slug": slug,
            "upstream_url": "http://example.com/mcp",
            "credentials": {"api_key": "test-key"},
            "is_public": False,
            "groups": [],
            "users": [],
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    server = response.json()
    try:
        yield server
    finally:
        client.delete(
            f"{ADMIN_MCP}/server/{server['id']}",
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )


def _user_servers(user: DATestUser) -> list[dict[str, Any]]:
    response = client.get(
        f"{USER_MCP}/servers", headers=user.headers, cookies=user.cookies
    )
    response.raise_for_status()
    return response.json()["mcp_servers"]


def test_admin_installs_a_pack_mcp(
    admin_user: DATestUser, installed_server: dict[str, Any]
) -> None:
    packs = client.get(
        f"{ADMIN_MCP}/packs", headers=admin_user.headers, cookies=admin_user.cookies
    )
    packs.raise_for_status()
    assert {
        "generic_http",
        "deepwiki",
        "context7",
        "parallel_search",
        "microsoft_learn",
    } <= {item["slug"] for item in packs.json()}
    assert installed_server["gateway_bound"] is True
    assert installed_server["catalog_slug"]
    assert installed_server["server_url"].endswith(
        f"/p/{installed_server['catalog_slug']}"
    )


def test_ungranted_user_cannot_see_a_private_org_mcp(
    basic_user: DATestUser, installed_server: dict[str, Any]
) -> None:
    slugs = {item.get("catalog_slug") for item in _user_servers(basic_user)}
    assert installed_server["catalog_slug"] not in slugs


def test_public_org_mcp_is_visible_to_everyone(
    admin_user: DATestUser, basic_user: DATestUser, installed_server: dict[str, Any]
) -> None:
    client.patch(
        f"{ADMIN_MCP}/server/{installed_server['id']}",
        json={"is_public": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    ).raise_for_status()
    slugs = {item.get("catalog_slug") for item in _user_servers(basic_user)}
    assert installed_server["catalog_slug"] in slugs


def test_group_grant_controls_visibility(
    admin_user: DATestUser, basic_user: DATestUser, installed_server: dict[str, Any]
) -> None:
    try:
        group = UserGroupManager.create(
            user_performing_action=admin_user, user_ids=[basic_user.id]
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 402:
            pytest.skip("User groups require the Business plan")
        raise
    UserGroupManager.wait_for_sync(
        user_groups_to_check=[group], user_performing_action=admin_user
    )
    client.patch(
        f"{ADMIN_MCP}/server/{installed_server['id']}",
        json={"is_public": False, "groups": [group.id]},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    ).raise_for_status()
    granted = {item.get("catalog_slug") for item in _user_servers(basic_user)}
    assert installed_server["catalog_slug"] in granted

    client.patch(
        f"{ADMIN_MCP}/server/{installed_server['id']}",
        json={"is_public": False, "groups": []},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    ).raise_for_status()
    revoked = {item.get("catalog_slug") for item in _user_servers(basic_user)}
    assert installed_server["catalog_slug"] not in revoked


def test_module_off_hides_bound_org_mcp(
    admin_user: DATestUser, basic_user: DATestUser, installed_server: dict[str, Any]
) -> None:
    client.patch(
        f"{ADMIN_MCP}/server/{installed_server['id']}",
        json={"is_public": True},
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    ).raise_for_status()
    assert installed_server["catalog_slug"] in {
        item.get("catalog_slug") for item in _user_servers(basic_user)
    }
    _set_module_enabled(admin_user, False)
    slugs = {item.get("catalog_slug") for item in _user_servers(basic_user)}
    assert installed_server["catalog_slug"] not in slugs
    _set_module_enabled(admin_user, True)


def test_basic_user_cannot_manage_org_mcp(basic_user: DATestUser) -> None:
    response = client.get(
        f"{ADMIN_MCP}/servers",
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    )
    assert response.status_code in (401, 403)
