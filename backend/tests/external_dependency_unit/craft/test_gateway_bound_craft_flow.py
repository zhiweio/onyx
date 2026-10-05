"""P3 M2: gateway-bound MCP servers flow into craft end to end.

Covers the acceptance points that live e2e exercises against the deployed
stack, at the DB-resolution layer so regressions fail fast in CI:
- bind → craft injection (server appears for craft users, URL points at
  the gateway, credentials never leave the backend);
- hot reload (fingerprint changes when the binding/tools change);
- skill frontmatter allowlists narrow to the catalog slug;
- per-user opt-out still applies to gateway-bound servers.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from typing import Any

from onyx.db.enums import (
    MCPAuthenticationPerformer,
    MCPAuthenticationType,
    MCPTransport,
)
from onyx.db.mcp import (
    create_mcp_server__no_commit,
    update_mcp_server__no_commit,
)
from onyx.db.models import MCPServer, User
from onyx.server.features.build.sandbox.util.mcp_config import (
    craft_mcp_fingerprint,
    resolve_craft_mcp_servers,
)
from tests.external_dependency_unit.conftest import create_test_user


@pytest.fixture
def gateway_env(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:  # noqa: ARG001
    # These are read at import time in app_configs; patch where consumed.
    monkeypatch.setattr("onyx.mcp_gateway.service.MCP_GATEWAY_ENABLED", True)
    monkeypatch.setattr(
        "onyx.mcp_gateway.tokens.MCP_GATEWAY_INTERNAL_TOKEN", "test-signing-secret"
    )
    monkeypatch.setattr(
        "onyx.server.features.build.sandbox.util.mcp_config.MCP_GATEWAY_PUBLIC_URL",
        "http://mcp_gateway:8091",
        raising=False,
    )
    # The module gate is env AND the KV setting; flip the KV row so
    # is_gateway_enabled() holds for this test's tenant.
    from onyx.server.settings.models import Settings
    from onyx.server.settings.store import load_settings, store_settings

    settings = load_settings()
    payload: dict[str, Any] = settings.model_dump()
    payload["mcp_gateway_enabled"] = True
    store_settings(Settings(**payload))


def _bind_server(
    db_session: Session,
    *,
    slug: str,
    available_in_craft: bool = True,
) -> MCPServer:
    """An org MCPServer bound to the gateway (the B-track shape)."""
    from onyx.server.features.mcp.gateway_bind import bind_org_server_to_gateway
    from onyx.server.features.mcp.models import MCPGatewayBindingRequest

    server = create_mcp_server__no_commit(
        owner_email="admin@example.com",
        name=f"gw-{slug}",
        description=None,
        server_url=f"https://upstream-{slug}.example.com/mcp",
        auth_type=MCPAuthenticationType.API_TOKEN,
        transport=MCPTransport.STREAMABLE_HTTP,
        auth_performer=MCPAuthenticationPerformer.ADMIN,
        db_session=db_session,
    )
    update_mcp_server__no_commit(
        server_id=server.id,
        db_session=db_session,
        available_in_craft=available_in_craft,
    )
    bind_org_server_to_gateway(
        db_session,
        server,
        MCPGatewayBindingRequest(
            slug=slug,
            upstream_url=f"https://upstream-{slug}.example.com/mcp",
            credentials={"api_key": "sk-secret"},
        ),
    )
    db_session.commit()
    db_session.refresh(server)
    return server


@pytest.fixture
def bound_server(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    gateway_env: None,  # noqa: ARG001
) -> Generator[MCPServer, None, None]:
    yield _bind_server(db_session, slug=f"tianyancha-{uuid4().hex[:6]}")


def test_bound_server_reaches_craft_injection(
    db_session: Session, bound_server: MCPServer
) -> None:
    user = create_test_user(db_session, f"gw-{uuid4().hex[:8]}")
    servers = resolve_craft_mcp_servers(db_session, user)
    matched = [s for s in servers if s.server_id == bound_server.id]
    assert matched, "gateway-bound craft-enabled server must be injected"
    entry = matched[0]
    assert "/p/" in entry.url or "mcp_gateway" in entry.url
    # URL-only config: credentials live in the backend, injected by the proxy.
    assert "sk-secret" not in str(entry.url)
    assert not any("sk-secret" in str(v) for v in (entry.headers or {}).values())


def test_unavailable_in_craft_is_excluded(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    gateway_env: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, f"gw-{uuid4().hex[:8]}")
    server = _bind_server(
        db_session, slug=f"hidden-{uuid4().hex[:6]}", available_in_craft=False
    )
    servers = resolve_craft_mcp_servers(db_session, user)
    assert all(s.server_id != server.id for s in servers)


def test_fingerprint_changes_on_binding_flip(
    db_session: Session, bound_server: MCPServer
) -> None:
    user: User = create_test_user(db_session, f"gw-{uuid4().hex[:8]}")
    before = craft_mcp_fingerprint(resolve_craft_mcp_servers(db_session, user))
    update_mcp_server__no_commit(
        server_id=bound_server.id,
        db_session=db_session,
        available_in_craft=False,
    )
    db_session.commit()
    after = craft_mcp_fingerprint(resolve_craft_mcp_servers(db_session, user))
    assert before != after, "admin flips must change the fingerprint (hot reload)"


def test_per_user_opt_out_applies_to_bound_server(
    db_session: Session, bound_server: MCPServer
) -> None:
    from onyx.db.models import MCPServer__UserDisabled

    user = create_test_user(db_session, f"gw-{uuid4().hex[:8]}")
    db_session.add(
        MCPServer__UserDisabled(mcp_server_id=bound_server.id, user_id=user.id)
    )
    db_session.commit()
    servers = resolve_craft_mcp_servers(db_session, user)
    assert all(s.server_id != bound_server.id for s in servers)


def test_skill_slug_allowlist_narrows_to_bound_server(
    db_session: Session, bound_server: MCPServer
) -> None:
    """A skill's required-mcp catalog slug unlocks exactly that server."""
    from tests.external_dependency_unit.craft.db_helpers import make_user

    user = make_user(db_session)
    slug = bound_server.catalog_entry.slug if bound_server.catalog_entry else None
    assert slug, "binding must create a catalog entry"
    allowed = _resolve_with_declared(db_session, user, {slug})
    assert allowed == {bound_server.id}


def _resolve_with_declared(
    db_session: Session, user: User, declared_slugs: set[str]
) -> set[int]:
    """The slug half of resolve_effective_mcp_server_ids: which craft
    servers match a skill's declared catalog slugs."""
    from onyx.db.mcp import get_craft_enabled_mcp_servers

    servers = get_craft_enabled_mcp_servers(db_session, user)
    return {
        server.id
        for server in servers
        if server.catalog_entry is not None
        and server.catalog_entry.slug in declared_slugs
    }
