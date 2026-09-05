import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayCallOutcome, MCPTransport
from onyx.db.mcp_gateway import (
    create_provider__no_commit,
    delete_cache_entries,
    delete_provider,
    get_provider_by_slug,
)
from onyx.db.models import MCPGatewayCallLog, MCPGatewayCachePolicy, MCPGatewayProvider
from onyx.mcp_gateway.engine import invoke_tool
from onyx.mcp_gateway.protocol import _tools_for_slug, invalidate_tools_cache
from onyx.mcp_gateway.upstream import list_upstream_tools
from shared_configs.contextvars import get_current_tenant_id

MCP_SERVER_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "integration"
    / "mock_services"
    / "mcp_test_server"
    / "run_mcp_server_no_auth.py"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen[bytes]) -> None:
    start = time.monotonic()
    while time.monotonic() - start < 15:
        if process.poll() is not None:
            raise RuntimeError("mock MCP server exited during startup")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)
    raise TimeoutError("mock MCP server did not accept connections")


@pytest.fixture
def mock_mcp_url() -> Generator[str, None, None]:
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, str(MCP_SERVER_SCRIPT), str(port)],
        cwd=MCP_SERVER_SCRIPT.parent,
    )
    try:
        _wait_for_port(port, process)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture
def live_provider(
    db_session: Session, tenant_context: None, mock_mcp_url: str
) -> Generator[MCPGatewayProvider, None, None]:
    slug = f"live-{uuid4().hex[:10]}"
    provider = create_provider__no_commit(
        db_session,
        slug=slug,
        display_name=slug,
        pack_slug="generic_http",
        upstream_url=mock_mcp_url,
        transport=MCPTransport.STREAMABLE_HTTP,
        auth_adapter=MCPGatewayAuthAdapter.BEARER,
        credentials={},
    )
    db_session.commit()
    try:
        yield provider
    finally:
        invalidate_tools_cache(slug)
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
async def test_tools_list_matches_upstream(
    live_provider: MCPGatewayProvider, tenant_context: None
) -> None:
    upstream = await list_upstream_tools(live_provider)
    gateway = await _tools_for_slug(live_provider.slug)
    assert [item.name for item in gateway] == [item.name for item in upstream]
    assert [item.inputSchema for item in gateway] == [
        item.inputSchema for item in upstream
    ]
    assert "hello" in {item.name for item in gateway}


@pytest.mark.asyncio
async def test_two_identical_calls_bill_upstream_once(
    live_provider: MCPGatewayProvider, tenant_context: None
) -> None:
    first = await invoke_tool(
        provider_slug=live_provider.slug,
        tool_name="hello",
        arguments={"name": "Ada"},
        user_email="a@example.com",
    )
    second = await invoke_tool(
        provider_slug=live_provider.slug,
        tool_name="hello",
        arguments={"name": "Ada"},
        user_email="b@example.com",
    )
    assert first.outcome == MCPGatewayCallOutcome.MISS
    assert first.upstream_billed is True
    assert second.outcome == MCPGatewayCallOutcome.HIT
    assert second.upstream_billed is False
    assert "Hello, Ada" in str(first.result)
    assert first.result == second.result
