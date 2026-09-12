import socket
import subprocess
import sys
import time
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import MCPGatewayAuthAdapter, MCPGatewayCallOutcome, MCPTransport
from onyx.db.mcp_catalog import (
    create_catalog_entry__no_commit,
    delete_catalog_entry,
    get_catalog_entry_by_slug,
)
from onyx.db.mcp_gateway import delete_cache_entries
from onyx.db.mcp_iceberg import (
    delete_catalog_calls,
    ensure_mcp_iceberg_tables,
    get_result,
    list_calls,
)
from onyx.db.models import MCPCatalogEntry
from onyx.mcp_gateway.engine import invoke_tool
from onyx.mcp_gateway.protocol import invalidate_tools_cache, tools_for_slug
from onyx.mcp_gateway.upstream import UpstreamTarget, list_upstream_tools
from shared_configs.contextvars import get_current_tenant_id

MCP_SERVER_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "integration"
    / "mock_services"
    / "mcp_test_server"
    / "run_mcp_server_no_auth.py"
)


@pytest.fixture(autouse=True)
def allow_loopback_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.mcp.ssrf.validate_mcp_outbound_url",
        lambda url, resolve_dns=True: url,
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
def live_entry(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    mock_mcp_url: str,
) -> Generator[MCPCatalogEntry, None, None]:
    slug = f"live-{uuid4().hex[:10]}"
    entry = create_catalog_entry__no_commit(
        db_session,
        slug=slug,
        display_name=slug,
        description=None,
        upstream_url=mock_mcp_url,
        transport=MCPTransport.STREAMABLE_HTTP,
        auth_adapter=MCPGatewayAuthAdapter.BEARER,
        credentials={},
        pack_slug="generic_http",
    )
    db_session.commit()
    ensure_mcp_iceberg_tables()
    try:
        yield entry
    finally:
        invalidate_tools_cache(get_current_tenant_id(), slug)
        delete_cache_entries(db_session, catalog_slug=slug)
        db_session.commit()
        delete_catalog_calls(slug)
        fresh = get_catalog_entry_by_slug(db_session, slug)
        if fresh is not None:
            delete_catalog_entry(db_session, fresh)


@pytest.mark.asyncio
async def test_tools_list_matches_upstream(
    live_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    upstream = await list_upstream_tools(UpstreamTarget.from_entry(live_entry))
    gateway = await tools_for_slug(get_current_tenant_id(), live_entry.slug)
    assert [item.name for item in gateway] == [item.name for item in upstream]
    assert [item.inputSchema for item in gateway] == [
        item.inputSchema for item in upstream
    ]
    assert "hello" in {item.name for item in gateway}


@pytest.mark.asyncio
async def test_two_identical_calls_bill_upstream_once(
    live_entry: MCPCatalogEntry,
    tenant_context: None,  # noqa: ARG001
) -> None:
    first = await invoke_tool(
        catalog_slug=live_entry.slug,
        tool_name="hello",
        arguments={"name": "Ada"},
        user_email="a@example.com",
    )
    second = await invoke_tool(
        catalog_slug=live_entry.slug,
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

    now = datetime.now(timezone.utc)
    rows, total = list_calls(
        from_time=now - timedelta(hours=1),
        to_time=now + timedelta(hours=1),
        catalog_slug=live_entry.slug,
        limit=10,
        offset=0,
    )
    assert total >= 2
    miss = next(row for row in rows if row.outcome == "miss")
    hit = next(row for row in rows if row.outcome == "hit")
    assert miss.result_blob_id
    assert miss.request_id
    assert miss.cache_key == hit.cache_key
    loaded = get_result(miss.result_blob_id, catalog_slug=live_entry.slug)
    assert loaded is not None
    assert loaded.payload == first.result
