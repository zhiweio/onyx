from types import SimpleNamespace
from typing import cast

import pytest

from onyx.db.enums import MCPServerScope
from onyx.db.mcp import (
    get_org_mcp_servers_accessible_to_user,
    user_can_invoke_mcp_server,
)
from onyx.db.models import MCPServer, User


def _user(email: str) -> User:
    return cast(User, SimpleNamespace(email=email))


def _server(scope: MCPServerScope, owner: str) -> MCPServer:
    return cast(MCPServer, SimpleNamespace(scope=scope, owner=owner))


def test_personal_server_is_owner_only() -> None:
    owner = _user("owner@example.com")
    other = _user("other@example.com")
    server = _server(MCPServerScope.PERSONAL, "owner@example.com")
    assert user_can_invoke_mcp_server(owner, server) is True
    assert user_can_invoke_mcp_server(other, server) is False


def test_org_server_is_not_blocked_here() -> None:
    user = _user("anyone@example.com")
    server = _server(MCPServerScope.USER, "admin@example.com")
    assert user_can_invoke_mcp_server(user, server) is True


def test_org_gallery_list_drops_personal_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    personal = _server(MCPServerScope.PERSONAL, "owner@example.com")
    org = _server(MCPServerScope.USER, "admin@example.com")
    monkeypatch.setattr(
        "onyx.db.mcp.get_mcp_servers_accessible_to_user",
        lambda user, db, include_system=None: [personal, org],
    )
    assert get_org_mcp_servers_accessible_to_user(_user("owner@example.com"), None) == [
        org
    ]
