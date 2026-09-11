from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from onyx.db.models import MCPServer as DbMCPServer
from onyx.db.models import User
from onyx.server.features.mcp.api import _refresh_stored_mcp_tools


def test_refresh_uses_upstream_for_gateway_bound_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovered: list[int] = []

    def fake_discover(
        db_session: object, entry: object, mcp_server_id: int
    ) -> str | None:
        discovered.append(mcp_server_id)
        return None

    listed: list[int] = []

    def fake_list(
        server_id: int,
        db: object,
        is_admin: bool,
        user: object,
    ) -> None:
        listed.append(server_id)

    monkeypatch.setattr(
        "onyx.server.features.mcp.api.discover_and_store_bound_tools",
        fake_discover,
    )
    monkeypatch.setattr(
        "onyx.server.features.mcp.api._list_mcp_tools_by_id",
        fake_list,
    )

    bound = cast(
        DbMCPServer,
        SimpleNamespace(id=11, catalog_entry=SimpleNamespace(slug="hithink-meta")),
    )
    direct = cast(
        DbMCPServer,
        SimpleNamespace(id=22, catalog_entry=None),
    )
    user = cast(User, SimpleNamespace(email="admin@example.com"))

    _refresh_stored_mcp_tools(bound, cast(Any, None), user, is_admin=True)
    _refresh_stored_mcp_tools(direct, cast(Any, None), user, is_admin=True)

    assert discovered == [11]
    assert listed == [22]


def test_refresh_surfaces_upstream_discovery_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "onyx.server.features.mcp.api.discover_and_store_bound_tools",
        lambda *args, **kwargs: "upstream timeout",
    )
    server = cast(
        DbMCPServer,
        SimpleNamespace(id=11, catalog_entry=SimpleNamespace(slug="qcc-company")),
    )
    user = cast(User, SimpleNamespace(email="admin@example.com"))
    with pytest.raises(HTTPException) as error:
        _refresh_stored_mcp_tools(server, cast(Any, None), user, is_admin=True)
    assert error.value.status_code == 502
    assert error.value.detail == "upstream timeout"
