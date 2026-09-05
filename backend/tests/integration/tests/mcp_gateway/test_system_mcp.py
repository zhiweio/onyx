"""System MCP end to end: module toggle, install, RBAC, and enablement.

These are the four behaviours the redesign promises, so they are checked
against a real deployment rather than in isolation.
"""

from collections.abc import Generator
from typing import Any
from uuid import uuid4

import pytest

from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.managers.user_group import UserGroupManager
from tests.integration.common_utils.test_models import DATestUser

CATALOG_BASE = f"{API_SERVER_URL}/admin/mcp-catalog"
USER_BASE = f"{API_SERVER_URL}/mcp-catalog"
SETTINGS_URL = f"{API_SERVER_URL}/admin/settings"


def _settings(user: DATestUser) -> dict[str, Any]:
    response = client.get(SETTINGS_URL, headers=user.headers, cookies=user.cookies)
    response.raise_for_status()
    return response.json()


def _set_module_enabled(user: DATestUser, enabled: bool) -> bool:
    """Flip the module toggle. Returns False when the gateway is not deployed."""
    current = _settings(user)
    response = client.patch(
        SETTINGS_URL,
        json={**current, "mcp_gateway_enabled": enabled},
        headers=user.headers,
        cookies=user.cookies,
    )
    if enabled and response.status_code == 400:
        return False
    response.raise_for_status()
    return True


@pytest.fixture
def gateway_enabled(admin_user: DATestUser) -> Generator[None, None, None]:
    if not _set_module_enabled(admin_user, True):
        pytest.skip("MCP_GATEWAY_ENABLED is not set on this deployment")
    try:
        yield
    finally:
        _set_module_enabled(admin_user, False)


@pytest.fixture
def installed_entry(
    admin_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> Generator[dict[str, Any], None, None]:
    slug = f"itest-{uuid4().hex[:8]}"
    response = client.post(
        f"{CATALOG_BASE}/entries",
        json={
            "slug": slug,
            "pack_slug": "generic_http",
            "upstream_url": "http://127.0.0.1:9/mcp",
            "credentials": {"api_key": "test-key"},
            "enabled": True,
            "is_public": False,
            "group_ids": [],
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    entry = response.json()
    try:
        yield entry
    finally:
        client.delete(
            f"{CATALOG_BASE}/entries/{entry['id']}",
            headers=admin_user.headers,
            cookies=admin_user.cookies,
        )


def _patch_entry(
    admin_user: DATestUser, entry_id: int, body: dict[str, Any]
) -> dict[str, Any]:
    response = client.patch(
        f"{CATALOG_BASE}/entries/{entry_id}",
        json=body,
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return response.json()


def _user_servers(user: DATestUser) -> list[dict[str, Any]]:
    response = client.get(
        f"{USER_BASE}/servers", headers=user.headers, cookies=user.cookies
    )
    response.raise_for_status()
    return response.json()


def test_admin_installs_a_system_mcp(
    admin_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    packs = client.get(
        f"{CATALOG_BASE}/packs", headers=admin_user.headers, cookies=admin_user.cookies
    )
    packs.raise_for_status()
    assert {"generic_http", "patsnap", "qixinbao", "tianyancha"} <= {
        item["slug"] for item in packs.json()
    }

    # The catalog entry projects into a server that points at the gateway, and
    # the shared credentials never come back over the wire.
    assert installed_entry["gateway_url"].endswith(f"/p/{installed_entry['slug']}")
    assert installed_entry["mcp_server_id"] is not None
    assert installed_entry["has_credentials"] is True
    assert "credentials" not in installed_entry

    policies = client.get(
        f"{CATALOG_BASE}/entries/{installed_entry['id']}/policies",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    policies.raise_for_status()
    assert "*" in {item["label"] for item in policies.json()}


def test_ungranted_user_cannot_see_a_private_system_mcp(
    basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    slugs = {item["catalog_slug"] for item in _user_servers(basic_user)}
    assert installed_entry["slug"] not in slugs


def test_public_entry_is_visible_to_everyone(
    admin_user: DATestUser, basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    _patch_entry(admin_user, installed_entry["id"], {"is_public": True})
    slugs = {item["catalog_slug"] for item in _user_servers(basic_user)}
    assert installed_entry["slug"] in slugs


def test_group_grant_controls_visibility(
    admin_user: DATestUser, basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    group = UserGroupManager.create(
        user_performing_action=admin_user, user_ids=[basic_user.id]
    )
    UserGroupManager.wait_for_sync(
        user_groups_to_check=[group], user_performing_action=admin_user
    )

    _patch_entry(admin_user, installed_entry["id"], {"group_ids": [group.id]})
    granted = {item["catalog_slug"] for item in _user_servers(basic_user)}
    assert installed_entry["slug"] in granted

    # Revoking the grant takes it away again.
    _patch_entry(admin_user, installed_entry["id"], {"group_ids": []})
    revoked = {item["catalog_slug"] for item in _user_servers(basic_user)}
    assert installed_entry["slug"] not in revoked


def test_user_enablement_is_separate_from_access(
    admin_user: DATestUser, basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    """A grant makes a server available; the user still has to switch it on."""
    _patch_entry(admin_user, installed_entry["id"], {"is_public": True})

    servers = _user_servers(basic_user)
    server = next(
        item for item in servers if item["catalog_slug"] == installed_entry["slug"]
    )
    assert server["enabled_for_user"] is False

    response = client.put(
        f"{USER_BASE}/servers/{server['mcp_server_id']}/enabled",
        json={"enabled": True},
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    )
    response.raise_for_status()

    refreshed = next(
        item
        for item in _user_servers(basic_user)
        if item["catalog_slug"] == installed_entry["slug"]
    )
    assert refreshed["enabled_for_user"] is True


def test_enabling_a_server_you_cannot_reach_is_refused(
    basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    response = client.put(
        f"{USER_BASE}/servers/{installed_entry['mcp_server_id']}/enabled",
        json={"enabled": True},
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    )
    assert response.status_code == 404


def test_module_toggle_hides_system_mcp(
    admin_user: DATestUser, basic_user: DATestUser, installed_entry: dict[str, Any]
) -> None:
    """The lego-brick promise: off means gone, for everyone."""
    _patch_entry(admin_user, installed_entry["id"], {"is_public": True})
    assert installed_entry["slug"] in {
        item["catalog_slug"] for item in _user_servers(basic_user)
    }

    _set_module_enabled(admin_user, False)
    assert _user_servers(basic_user) == []

    _set_module_enabled(admin_user, True)
    assert installed_entry["slug"] in {
        item["catalog_slug"] for item in _user_servers(basic_user)
    }


def test_basic_user_cannot_manage_the_catalog(basic_user: DATestUser) -> None:
    response = client.get(
        f"{CATALOG_BASE}/entries",
        headers=basic_user.headers,
        cookies=basic_user.cookies,
    )
    assert response.status_code in (401, 403)
