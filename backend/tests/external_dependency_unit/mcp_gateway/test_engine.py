import asyncio
from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.enums import (
    MCPGatewayAuthAdapter,
    MCPGatewayCallOutcome,
    MCPGatewayRefreshMode,
    MCPTransport,
)
from onyx.db.mcp_gateway import (
    create_provider__no_commit,
    delete_cache_entries,
    delete_provider,
    get_provider_by_slug,
    upsert_policy__no_commit,
)
from onyx.db.models import MCPGatewayCallLog, MCPGatewayCachePolicy, MCPGatewayProvider
from onyx.mcp_gateway.engine import invoke_tool
from shared_configs.contextvars import get_current_tenant_id


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
def gateway_provider(
    db_session: Session, tenant_context: None
) -> Generator[MCPGatewayProvider, None, None]:
    slug = f"gw-{uuid4().hex[:10]}"
    provider = create_provider__no_commit(
        db_session,
        slug=slug,
        display_name=slug,
        pack_slug="generic_http",
        upstream_url="http://127.0.0.1:9/mcp",
        transport=MCPTransport.STREAMABLE_HTTP,
        auth_adapter=MCPGatewayAuthAdapter.BEARER,
        credentials={},
    )
    db_session.commit()
    try:
        yield provider
    finally:
        tenant_id = get_current_tenant_id()
        delete_cache_entries(db_session, tenant_id=tenant_id, provider_slug=slug)
        db_session.execute(
            delete(MCPGatewayCallLog).where(MCPGatewayCallLog.provider_slug == slug)
        )
        db_session.execute(
            delete(MCPGatewayCachePolicy).where(
                MCPGatewayCachePolicy.provider_slug == slug
            )
        )
        fresh = get_provider_by_slug(db_session, slug)
        if fresh is not None:
            delete_provider(db_session, fresh)
        db_session.commit()


@pytest.mark.asyncio
async def test_second_call_hits_cache_and_is_not_billed(
    gateway_provider: MCPGatewayProvider,
    tenant_context: None,
) -> None:
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        return _ok_result(f"hit-{calls['n']}")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        first = await invoke_tool(
            provider_slug=gateway_provider.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
            user_email="a@example.com",
        )
        second = await invoke_tool(
            provider_slug=gateway_provider.slug,
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
    gateway_provider: MCPGatewayProvider,
    tenant_context: None,
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
                provider_slug=gateway_provider.slug,
                tool_name="hello",
                arguments={"name": "Ada"},
            ),
            invoke_tool(
                provider_slug=gateway_provider.slug,
                tool_name="hello",
                arguments={"name": "Ada"},
            ),
        )

    assert calls["n"] == 1
    assert left.result == right.result


@pytest.mark.asyncio
async def test_error_result_is_not_cached(
    gateway_provider: MCPGatewayProvider,
    tenant_context: None,
) -> None:
    calls = {"n": 0}

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        calls["n"] += 1
        return _err_result()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        first = await invoke_tool(
            provider_slug=gateway_provider.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )
        second = await invoke_tool(
            provider_slug=gateway_provider.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )

    assert first.upstream_billed is True
    assert second.upstream_billed is True
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_swr_returns_stale_and_enqueues_refresh(
    db_session: Session,
    gateway_provider: MCPGatewayProvider,
    tenant_context: None,
) -> None:
    upsert_policy__no_commit(
        db_session,
        provider_slug=gateway_provider.slug,
        tool_name="hello",
        refresh_mode=MCPGatewayRefreshMode.SWR,
        ttl_seconds=1,
        swr_seconds=3600,
        schedule_cron=None,
        key_fields=None,
        normalize=None,
        cache_empty_ttl_seconds=1,
        max_response_bytes=2_000_000,
    )
    db_session.commit()
    refresh_calls: list[str] = []

    async def fake_upstream(*_args: object, **_kwargs: object) -> dict:
        return _ok_result("first")

    def fake_enqueue(_tenant: str, cache_key: str) -> None:
        refresh_calls.append(cache_key)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("onyx.mcp_gateway.engine.call_upstream", fake_upstream)
        mp.setattr("onyx.mcp_gateway.engine.enqueue_refresh", fake_enqueue)
        first = await invoke_tool(
            provider_slug=gateway_provider.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )
        await asyncio.sleep(1.1)
        second = await invoke_tool(
            provider_slug=gateway_provider.slug,
            tool_name="hello",
            arguments={"name": "Ada"},
        )

    assert first.outcome == MCPGatewayCallOutcome.MISS
    assert second.outcome == MCPGatewayCallOutcome.SWR
    assert second.upstream_billed is False
    assert refresh_calls
