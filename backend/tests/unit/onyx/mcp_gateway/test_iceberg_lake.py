"""Iceberg lake writes and reads against a local file warehouse."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from onyx.mcp_gateway.lake.catalog import (
    ensure_mcp_iceberg_tables,
    reset_lake_for_tests,
)
from onyx.mcp_gateway.lake.io import (
    append_call,
    append_result,
    clear_tenant_lake,
    get_result,
    list_calls,
    stats_series,
)


@pytest.fixture
def isolated_lake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    monkeypatch.setenv("MCP_ICEBERG_WAREHOUSE", f"file://{tmp_path / 'warehouse'}")
    monkeypatch.setenv(
        "MCP_ICEBERG_CATALOG_URI", f"sqlite:///{tmp_path / 'catalog.db'}"
    )
    reset_lake_for_tests()
    ensure_mcp_iceberg_tables()
    try:
        yield
    finally:
        clear_tenant_lake(tenant_id="public")
        reset_lake_for_tests()


def test_result_round_trip(isolated_lake: None) -> None:  # noqa: ARG001
    payload = {"content": [{"type": "text", "text": "hello"}], "isError": False}
    record = append_result(
        blob_id="ab" + "0" * 62,
        catalog_slug="unit-lake",
        effective_tool_name="echo",
        payload=payload,
        digest={"kind": "test"},
        size_bytes=12,
        tenant_id="public",
    )
    loaded = get_result(record.blob_id, tenant_id="public", catalog_slug="unit-lake")
    assert loaded is not None
    assert loaded.payload == payload
    assert loaded.effective_tool_name == "echo"


def test_call_list_and_series(isolated_lake: None) -> None:  # noqa: ARG001
    now = datetime.now(timezone.utc)
    append_call(
        call_id=str(uuid4()),
        request_id=str(uuid4()),
        catalog_slug="unit-lake",
        pack_slug="test",
        tool_name="echo",
        effective_tool_name="echo",
        cache_key="k1",
        outcome="miss",
        upstream_billed=True,
        latency_ms=12,
        response_bytes=40,
        arguments={"q": "acme"},
        arguments_digest="q=acme",
        refresh_mode="ttl",
        ttl_seconds=60,
        tenant_id="public",
        created_at=now,
    )
    rows, total = list_calls(
        from_time=now - timedelta(hours=1),
        to_time=now + timedelta(hours=1),
        catalog_slug="unit-lake",
        tenant_id="public",
    )
    assert total == 1
    assert rows[0].arguments == {"q": "acme"}
    series = stats_series(
        from_time=now - timedelta(hours=1),
        to_time=now + timedelta(hours=1),
        catalog_slug="unit-lake",
        tenant_id="public",
    )
    assert series["calls_by_outcome"][0]["miss"] == 1
    assert series["billed_vs_saved"][0]["billed"] == 1
