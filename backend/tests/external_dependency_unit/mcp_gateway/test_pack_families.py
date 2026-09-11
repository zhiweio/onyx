"""Install pack families without live tool discovery."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from onyx.db.models import MCPCatalogEntry, MCPServer, User
from onyx.mcp_gateway.packs.hithink_finance import HITHINK_ENDPOINT_SLUGS
from onyx.mcp_gateway.packs.zhihuiya_endpoints import (
    ZHIHUIYA_ENDPOINT_SLUGS,
    ZHIHUIYA_STARTER,
)
from onyx.server.features.mcp.gateway_bind import create_org_servers_from_pack_family
from onyx.server.features.mcp.models import MCPFromPackRequest
from onyx.skills.effective_mcp import resolve_effective_mcp_server_ids
from tests.external_dependency_unit.conftest import create_test_user


def _mark_public(
    *,
    mcp_server: MCPServer,
    acting_user: User,  # noqa: ARG001
    is_public: bool | None,
    user_ids: list[UUID] | None,  # noqa: ARG001
    group_ids: list[int] | None,  # noqa: ARG001
    is_new: bool,  # noqa: ARG001
    db_session: Session,  # noqa: ARG001
) -> None:
    mcp_server.is_public = True if is_public is None else is_public


def _install_family(
    db_session: Session,
    user: User,
    pack_slug: str,
) -> list[tuple[MCPServer, MCPCatalogEntry, str | None]]:
    return create_org_servers_from_pack_family(
        db_session,
        user,
        MCPFromPackRequest(
            pack_slug=pack_slug,
            credentials={"api_key": "family-test-key"},
            is_public=True,
        ),
        apply_access=_mark_public,
        discover_tools=False,
    )


@pytest.fixture
def gateway_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.mcp.gateway_bind.is_gateway_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "onyx.mcp_gateway.tokens.gateway_signing_secret",
        lambda: "test-gateway-secret",
    )


def test_hithink_family_creates_six_servers(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    gateway_on: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "family_hithink", is_admin=True)
    created = _install_family(db_session, user, "hithink-finance")
    slugs = {entry.slug for _server, entry, _error in created}
    assert slugs == HITHINK_ENDPOINT_SLUGS
    assert all(server.available_in_craft for server, _entry, _error in created)


def test_zhihuiya_skill_enables_starter_only(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    gateway_on: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "family_zhihuiya", is_admin=True)
    created = _install_family(db_session, user, "zhihuiya")
    slugs = {entry.slug for _server, entry, _error in created}
    assert slugs == ZHIHUIYA_ENDPOINT_SLUGS
    assert "triz" not in slugs

    starter_ids = resolve_effective_mcp_server_ids(
        db_session, user, selected_skill_ids=["zhihuiya"]
    )
    starter_slugs = {
        entry.slug
        for _server, entry, _error in created
        if _server.id in set(starter_ids)
    }
    assert starter_slugs == set(ZHIHUIYA_STARTER)

    assert resolve_effective_mcp_server_ids(db_session, user) == []


def test_empty_turn_ignores_installed_family(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    gateway_on: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, "family_empty", is_admin=True)
    _install_family(db_session, user, "hithink-finance")
    assert resolve_effective_mcp_server_ids(db_session, user) == []
    assert (
        resolve_effective_mcp_server_ids(
            db_session, user, selected_skill_ids=[], selected_mcp_server_ids=[]
        )
        == []
    )
