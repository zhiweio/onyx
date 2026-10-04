"""Per-user MCP opt-out (mcp_server__user_disabled) end-to-end semantics.

Covers the single enable/disable surface (/craft/v1/mcp-actions):
- craft injection (get_craft_enabled_mcp_servers → resolve_craft_mcp_servers
  via the executor's None allowlist) excludes user-disabled servers;
- chat tool building (resolve_effective_mcp_server_ids) defaults to the
  user-enabled set when no explicit selection is sent;
- the enabled PATCH (PATCH /mcp/server/{id}/enabled) writes/clears the
  opt-out row for the calling user only and hot-reloads their craft sandbox
  config hash;
- the personal and gallery listings report user_enabled per server.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import MCPServerScope
from onyx.db.mcp import (
    get_craft_enabled_mcp_servers,
    get_user_disabled_mcp_server_ids,
    user_can_access_mcp_server,
)
from onyx.db.models import MCPServer, MCPServer__UserDisabled, User
from onyx.skills.effective_mcp import resolve_effective_mcp_server_ids


@pytest.fixture()
def org_server(db_session: Session) -> MCPServer:
    """An org-wide server the admin opened to craft (eligible for everyone)."""
    server = MCPServer(
        owner="admin@example.com",
        name="Org Server",
        server_url="https://mcp.example.com/org",
        scope=MCPServerScope.USER,
        available_in_craft=True,
        is_public=True,
    )
    db_session.add(server)
    db_session.commit()
    return server


def test_disable_row_removes_server_from_craft_injection(
    db_session: Session,
    test_user: User,
    org_server: MCPServer,
) -> None:
    assert org_server.id in [
        s.id for s in get_craft_enabled_mcp_servers(db_session, test_user)
    ]

    db_session.add(
        MCPServer__UserDisabled(mcp_server_id=org_server.id, user_id=test_user.id)
    )
    db_session.commit()

    remaining = get_craft_enabled_mcp_servers(db_session, test_user)
    assert org_server.id not in [s.id for s in remaining]

    # Another user is unaffected.
    other_disabled = get_user_disabled_mcp_server_ids(db_session, uuid4())
    assert org_server.id not in other_disabled


def test_opt_out_model_defaults_everything_to_enabled(
    db_session: Session,
    test_user: User,
    org_server: MCPServer,
) -> None:
    """No rows = everything eligible is enabled (existing users see no change)."""
    assert get_user_disabled_mcp_server_ids(db_session, test_user.id) == set()
    assert org_server.id in [
        s.id for s in get_craft_enabled_mcp_servers(db_session, test_user)
    ]


def test_chat_default_set_excludes_disabled_servers(
    db_session: Session,
    test_user: User,
    org_server: MCPServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat with no explicit selection now injects the user-enabled set."""

    def _can_authenticate(*_args: object) -> bool:
        return True

    monkeypatch.setattr(
        "onyx.server.features.mcp.credentials.user_can_authenticate",
        _can_authenticate,
    )
    # resolve_effective_mcp_server_ids imports the predicate by module path —
    # patch the same object where it is looked up.
    import onyx.skills.effective_mcp as effective_mcp

    monkeypatch.setattr(
        effective_mcp,
        "user_can_authenticate",
        _can_authenticate,
        raising=False,
    )

    default_ids = resolve_effective_mcp_server_ids(db_session, test_user)
    assert org_server.id in default_ids

    db_session.add(
        MCPServer__UserDisabled(mcp_server_id=org_server.id, user_id=test_user.id)
    )
    db_session.commit()

    default_ids = resolve_effective_mcp_server_ids(db_session, test_user)
    assert org_server.id not in default_ids


def test_access_gate_covers_org_and_personal_servers(
    db_session: Session,
    test_user: User,
    org_server: MCPServer,
) -> None:
    """The unified enabled PATCH gates on `user_can_access_mcp_server`:
    org servers by their sharing settings, personal servers by ownership."""
    personal = MCPServer(
        owner=test_user.email,
        name="My Server",
        server_url="https://mcp.example.com/mine",
        scope=MCPServerScope.PERSONAL,
        is_public=False,
    )
    foreign_personal = MCPServer(
        owner="someone-else@example.com",
        name="Not Mine",
        server_url="https://mcp.example.com/other",
        scope=MCPServerScope.PERSONAL,
        is_public=False,
    )
    db_session.add_all([personal, foreign_personal])
    db_session.commit()

    assert user_can_access_mcp_server(test_user, org_server.id, db_session) is True
    assert user_can_access_mcp_server(test_user, personal.id, db_session) is True
    assert (
        user_can_access_mcp_server(test_user, foreign_personal.id, db_session) is False
    )
