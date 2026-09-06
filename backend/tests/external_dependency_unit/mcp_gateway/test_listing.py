"""Offset pages for gateway cache and call lists stay disjoint."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.enums import MCPGatewayCallOutcome
from onyx.db.mcp_gateway import (
    count_cache_entries,
    count_call_logs,
    delete_blobs,
    delete_cache_entries,
    insert_call_log__no_commit,
    list_cache_entries,
    list_call_logs,
    upsert_cache_entry__no_commit,
)
from onyx.db.models import MCPGatewayCallLog
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.storage import store_result

_PAGE = 20
_TOTAL = 25
_INLINE = CachePolicySpec(inline_threshold_bytes=32_768)


@pytest.fixture
def listing_slug(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> Generator[str, None, None]:
    slug = f"page-{uuid4().hex[:10]}"
    stored = store_result(
        db_session,
        {
            "content": [{"type": "text", "text": "page"}],
            "structuredContent": None,
            "isError": False,
        },
        _INLINE,
        catalog_slug=slug,
        tool_name="list-tool",
    )
    assert stored is not None
    base = datetime.now(timezone.utc)
    for index in range(_TOTAL):
        cache_key = sha256(f"{slug}:{index}".encode()).hexdigest()
        tool_name = "uniq-page-tool" if index == 0 else "list-tool"
        entry = upsert_cache_entry__no_commit(
            db_session,
            cache_key=cache_key,
            catalog_slug=slug,
            tool_name=tool_name,
            effective_tool_name=tool_name,
            arguments={"n": index},
            blob_id=stored.blob_id,
            is_empty=False,
            last_refresh_status="ok",
        )
        entry.last_accessed_at = base + timedelta(seconds=index)
        call = insert_call_log__no_commit(
            db_session,
            catalog_slug=slug,
            tool_name=tool_name,
            effective_tool_name=tool_name,
            cache_key=cache_key,
            outcome=MCPGatewayCallOutcome.MISS,
            upstream_billed=True,
            latency_ms=index,
            response_bytes=8,
            user_email="admin@example.com",
            session_id=None,
            arguments={"n": index},
            result_blob_id=stored.blob_id,
            error_message=None,
        )
        call.created_at = base + timedelta(seconds=index)
    db_session.commit()
    try:
        yield slug
    finally:
        delete_cache_entries(db_session, catalog_slug=slug)
        db_session.execute(
            delete(MCPGatewayCallLog).where(MCPGatewayCallLog.catalog_slug == slug)
        )
        db_session.commit()
        delete_blobs(db_session, [stored.blob_id])


def test_cache_offset_pages_are_disjoint(
    db_session: Session,
    listing_slug: str,
    tenant_context: None,  # noqa: ARG001
) -> None:
    total = count_cache_entries(db_session, catalog_slug=listing_slug)
    assert total == _TOTAL

    first = list_cache_entries(
        db_session, catalog_slug=listing_slug, limit=_PAGE, offset=0
    )
    second = list_cache_entries(
        db_session, catalog_slug=listing_slug, limit=_PAGE, offset=_PAGE
    )
    first_keys = {row.cache_key for row in first}
    second_keys = {row.cache_key for row in second}

    assert len(first) == _PAGE
    assert len(second) == _TOTAL - _PAGE
    assert first_keys.isdisjoint(second_keys)
    assert len(first_keys | second_keys) == _TOTAL

    found = list_cache_entries(
        db_session, catalog_slug=listing_slug, q="uniq-page-tool", limit=_PAGE, offset=0
    )
    assert (
        count_cache_entries(db_session, catalog_slug=listing_slug, q="uniq-page-tool")
        == 1
    )
    assert len(found) == 1
    assert found[0].effective_tool_name == "uniq-page-tool"

    empty = list_cache_entries(
        db_session,
        catalog_slug=listing_slug,
        q="uniq-page-tool",
        limit=_PAGE,
        offset=_PAGE,
    )
    assert empty == []


def test_call_offset_pages_are_disjoint(
    db_session: Session,
    listing_slug: str,
    tenant_context: None,  # noqa: ARG001
) -> None:
    now = datetime.now(timezone.utc)
    from_time = now - timedelta(days=1)
    to_time = now + timedelta(days=1)
    total = count_call_logs(
        db_session,
        from_time=from_time,
        to_time=to_time,
        catalog_slug=listing_slug,
    )
    assert total == _TOTAL

    first = list_call_logs(
        db_session,
        from_time=from_time,
        to_time=to_time,
        catalog_slug=listing_slug,
        limit=_PAGE,
        offset=0,
    )
    second = list_call_logs(
        db_session,
        from_time=from_time,
        to_time=to_time,
        catalog_slug=listing_slug,
        limit=_PAGE,
        offset=_PAGE,
    )
    first_ids = {row.id for row in first}
    second_ids = {row.id for row in second}

    assert len(first) == _PAGE
    assert len(second) == _TOTAL - _PAGE
    assert first_ids.isdisjoint(second_ids)
    assert len(first_ids | second_ids) == _TOTAL
    assert first[0].created_at >= first[-1].created_at
    assert first[-1].created_at >= second[0].created_at

    found = list_call_logs(
        db_session,
        from_time=from_time,
        to_time=to_time,
        catalog_slug=listing_slug,
        q="uniq-page-tool",
        limit=_PAGE,
        offset=0,
    )
    assert (
        count_call_logs(
            db_session,
            from_time=from_time,
            to_time=to_time,
            catalog_slug=listing_slug,
            q="uniq-page-tool",
        )
        == 1
    )
    assert len(found) == 1
    assert found[0].effective_tool_name == "uniq-page-tool"
