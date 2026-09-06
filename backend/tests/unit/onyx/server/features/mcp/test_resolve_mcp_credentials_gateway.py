from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest

from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPServerScope,
)
from onyx.db.models import MCPServer, User
from onyx.server.features.mcp.credentials import (
    MCPCredentialsError,
    resolve_mcp_credentials,
)


def _user() -> User:
    user = MagicMock()
    user.email = "owner@example.com"
    user.is_anonymous = False
    user.oauth_accounts = []
    return cast(User, user)


def _server(**kwargs: object) -> MCPServer:
    return cast(MCPServer, SimpleNamespace(**kwargs))


def test_personal_never_mints_gateway_jwt() -> None:
    server = _server(
        id=1,
        scope=MCPServerScope.PERSONAL,
        catalog_entry=SimpleNamespace(slug="bound"),
        auth_type=MCPAuthenticationType.NONE,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
        admin_connection_config=None,
    )
    resolved = resolve_mcp_credentials(server, _user(), MagicMock(), user_configs={})
    assert resolved.system_catalog_slug is None


def test_org_binding_mints_gateway_jwt() -> None:
    server = _server(
        id=2,
        scope=MCPServerScope.USER,
        catalog_entry=SimpleNamespace(slug="docs"),
        auth_type=MCPAuthenticationType.API_TOKEN,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
    )
    resolved = resolve_mcp_credentials(server, _user(), MagicMock(), user_configs={})
    assert resolved.system_catalog_slug == "docs"


def test_org_direct_has_no_gateway_jwt() -> None:
    server = _server(
        id=3,
        scope=MCPServerScope.USER,
        catalog_entry=None,
        auth_type=MCPAuthenticationType.NONE,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
        admin_connection_config=None,
    )
    resolved = resolve_mcp_credentials(server, _user(), MagicMock(), user_configs={})
    assert resolved.system_catalog_slug is None


def test_binding_plus_per_user_is_rejected() -> None:
    server = _server(
        id=4,
        scope=MCPServerScope.USER,
        catalog_entry=SimpleNamespace(slug="docs"),
        auth_type=MCPAuthenticationType.API_TOKEN,
        auth_performer=MCPAuthenticationPerformer.PER_USER,
    )
    with pytest.raises(MCPCredentialsError):
        resolve_mcp_credentials(server, _user(), MagicMock(), user_configs={})
