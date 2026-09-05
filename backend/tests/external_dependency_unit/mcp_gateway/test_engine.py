import asyncio
from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayCallOutcome,
    MCPTransport,
)
from onyx.db.mcp_catalog import (
    create_catalog_entry__no_commit,
    delete_catalog_entry,
    get_catalog_entry_by_slug,
)
from onyx.db.mcp_gateway import delete_cache_entries
from onyx.db.models import MCPCatalogEntry, MCPGatewayCallLog
from onyx.mcp_gateway.engine import invoke_tool


def _ok_result(text: str) -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": None,
        "isError": False,
    }


def _err_result() -> dict:
    return {
        "content": [{"type": "text", "text": "upstream 502"}],
        "structuredContent": None,
        "isError": True,
    }


@pytest.fixture
def catalog_entry(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> Generator[MCPCatalogEntry, None, None]:
    slug = f"gw-{uuid4().hex[:10]}"
    entry = create_catalog_entry__no_commit(
        db_session,
        slug=slug,
        display_name=slug,
        description=None,
        upstream_url="http://127.0.0.1:9/mcp",
        transport=MCPTransport.STREAMABLE_HTTP,
        auth_adapter=MCPGatewayAuthAdapter.BEARER,
        credentials={},
        pack_slug="generic_http",
    )
    db_session.commit()
    try:
        yield entry
    finally:
        delete_cache_entries(db_session, catalog_slug=slug)
        db_session.execute(
            delete(MCPGatewayCallLog).where(MCPGatewayCallLog.catalog_slug == slug)
        )
        db_session.commit()
        fresh = get_catalog_entry_by_slug(db_session, slug)
        if fresh is not None:
            delete_catalog_entry(db_session, fresh)


def _with_overrides(
    db_session: Session, entry: MCPCatalogEntry, overrides: dict
) -> None:
    entry.policy_overrides = overrides
    db_session.commit()


@pytest.mark.asyncio
async def test_second_call_hits_cache_and_is_not_billed(
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        return _ok_result(f"hit-{calls['n']}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        first = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
            user_email="a@example.com",
        )
        # A different user must reuse the same cached answer: caching is per
        # tenant, not per user, which is the point of a shared system MCP.
        second = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
            user_email="b@example.com",
        )

    assert first.outcome == MCPGatewayCallOutcome.MISS
    assert first.upstream_billed is True
    assert second.outcome == MCPGatewayCallOutcome.HIT
    assert second.upstream_billed is False
    assert second.result == first.result
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_single_flight_calls_upstream_once(
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        await asyncio.sleep(0.2)
        return _ok_result("shared")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        left, right = await asyncio.gather(
            invoke_tool(
                catalog_slug=catalog_entry.slug,
                tool_name="hello",
                arguments={"name": "Ada"},
            ),
            invoke_tool(
                catalog_slug=catalog_entry.slug,
                tool_name="hello",
                arguments={"name": "Ada"},
            ),
        )

    assert calls["n"] == 1
    assert left.result == right.result


@pytest.mark.asyncio
async def test_error_result_is_not_cached(
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    """An error belongs to the attempt, not the arguments — never cache it."""
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        return _err_result()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        first = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )
        second = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )

    assert first.upstream_billed is True
    assert second.upstream_billed is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_swr_returns_stale_and_enqueues_refresh(
    db_session: Session,
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    _with_overrides(
        db_session,
        catalog_entry,
        {"hello": {"refresh_mode": "swr", "ttl_seconds": 1, "swr_seconds": 3600}},
    )
    refresh_calls: list[str] = []

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        return _ok_result("first")

    def fake_enqueue(_tenant: str, cache_key: str) -> None:
        refresh_calls.append(cache_key)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        mp.setattr("onyx.mcp_gateway.engine.enqueue_refresh", fake_enqueue)
        first = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )
        await asyncio.sleep(1.1)
        second = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )

    assert first.outcome == MCPGatewayCallOutcome.MISS
    assert second.outcome == MCPGatewayCallOutcome.SWR
    assert second.upstream_billed is False
    assert refresh_calls


@pytest.mark.asyncio
async def test_bypass_policy_never_caches(
    db_session: Session,
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    _with_overrides(db_session, catalog_entry, {"hello": {"refresh_mode": "bypass"}})
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        return _ok_result("live")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        first = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )
        second = await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )

    assert first.outcome == MCPGatewayCallOutcome.BYPASS
    assert second.outcome == MCPGatewayCallOutcome.BYPASS
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_disabled_entry_is_refused(
    db_session: Session,
    catalog_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    catalog_entry.enabled = False
    db_session.commit()

    with pytest.raises(ValueError):
        await invoke_tool(
            catalog_slug=catalog_entry.slug,
            tool_name="hello",
            arguments={},
        )
