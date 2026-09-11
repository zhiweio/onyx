"""Install a pack family through the admin HTTP API."""

from collections.abc import Generator
from typing import Any
from uuid import uuid4

import pytest

from onyx.mcp_gateway.packs.hithink_finance import HITHINK_ENDPOINT_SLUGS
from tests.integration.common_utils.constants import API_SERVER_URL
from tests.integration.common_utils.http_client import client
from tests.integration.common_utils.test_models import DATestUser

ADMIN_MCP = f"{API_SERVER_URL}/admin/mcp"
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


def _admin_servers(admin_user: DATestUser) -> list[dict[str, Any]]:
    response = client.get(
        f"{ADMIN_MCP}/servers",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    return response.json()["mcp_servers"]


def test_pack_list_includes_finance_families(admin_user: DATestUser) -> None:
    response = client.get(
        f"{ADMIN_MCP}/packs",
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    by_slug = {item["slug"]: item for item in response.json()}
    assert by_slug["hithink-finance"]["endpoint_count"] == 6
    assert by_slug["qichacha"]["endpoint_count"] == 10
    assert by_slug["zhihuiya"]["endpoint_count"] >= 30
    assert {ep["slug"] for ep in by_slug["hithink-finance"]["endpoints"]} == (
        HITHINK_ENDPOINT_SLUGS
    )


def test_from_pack_family_creates_hithink_servers(
    admin_user: DATestUser,
    gateway_enabled: None,  # noqa: ARG001
) -> None:
    existing = {
        item["catalog_slug"]: item
        for item in _admin_servers(admin_user)
        if item.get("catalog_slug") in HITHINK_ENDPOINT_SLUGS
    }
    if set(existing) == HITHINK_ENDPOINT_SLUGS:
        assert all(item["available_in_craft"] for item in existing.values())
        assert all(item["gateway_bound"] for item in existing.values())
        return

    response = client.post(
        f"{ADMIN_MCP}/servers/from-pack-family",
        json={
            "pack_slug": "hithink-finance",
            "credentials": {"api_key": f"itest-{uuid4().hex[:8]}"},
            "is_public": True,
            "groups": [],
            "users": [],
            "discover_tools": False,
        },
        headers=admin_user.headers,
        cookies=admin_user.cookies,
    )
    response.raise_for_status()
    servers: list[dict[str, Any]] = response.json()
    new_ids = [
        item["id"] for item in servers if item.get("catalog_slug") not in existing
    ]
    try:
        slugs = {item["catalog_slug"] for item in servers}
        assert slugs == HITHINK_ENDPOINT_SLUGS
        assert all(item["available_in_craft"] for item in servers)
        assert all(item["gateway_bound"] for item in servers)
    finally:
        for server_id in new_ids:
            client.delete(
                f"{ADMIN_MCP}/server/{server_id}",
                headers=admin_user.headers,
                cookies=admin_user.cookies,
            )
