"""Iceberg result persist, content-hash dedup, and digest determinism.

These need Postgres and the Iceberg catalog, so they are external-dependency
tests rather than unit tests.
"""

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import MCPResultStorage
from onyx.db.mcp_gateway import delete_blobs
from onyx.db.mcp_iceberg import delete_results
from onyx.mcp_gateway.digest import build_digest, extract_path
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.storage import (
    canonical_bytes,
    content_hash,
    load_result,
    store_result,
)

_POLICY = CachePolicySpec(inline_threshold_bytes=32_768)


def _payload(text: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": {"items": [{"id": 1, "name": "Acme"}], "total": 1},
        "isError": False,
    }


@pytest.fixture
def stored_blob_ids(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> Generator[list[str], None, None]:
    created: list[str] = []
    try:
        yield created
    finally:
        if created:
            delete_results(created)
            delete_blobs(db_session, created)


def test_result_round_trips_through_iceberg(
    db_session: Session,
    stored_blob_ids: list[str],
    tenant_context: None,  # noqa: ARG001
) -> None:
    stored = store_result(
        db_session,
        _payload("small"),
        _POLICY,
        catalog_slug="iceberg-roundtrip",
        tool_name="echo",
    )
    db_session.commit()
    assert stored is not None
    stored_blob_ids.append(stored.blob_id)

    assert stored.storage == MCPResultStorage.ICEBERG
    assert stored.file_id is None

    loaded = load_result(db_session, stored.blob_id)
    db_session.commit()
    assert loaded is not None
    assert loaded.payload == _payload("small")
    assert loaded.storage == MCPResultStorage.ICEBERG


def test_large_result_also_lives_in_iceberg(
    db_session: Session,
    stored_blob_ids: list[str],
    tenant_context: None,  # noqa: ARG001
) -> None:
    payload = _payload("x" * 50_000)
    stored = store_result(
        db_session,
        payload,
        CachePolicySpec(inline_threshold_bytes=1_024),
        catalog_slug="iceberg-large",
        tool_name="echo",
    )
    db_session.commit()
    assert stored is not None
    stored_blob_ids.append(stored.blob_id)

    assert stored.storage == MCPResultStorage.ICEBERG
    assert stored.file_id is None

    loaded = load_result(db_session, stored.blob_id)
    db_session.commit()
    assert loaded is not None
    assert loaded.payload == payload


def test_same_body_is_stored_once(
    db_session: Session,
    stored_blob_ids: list[str],
    tenant_context: None,  # noqa: ARG001
) -> None:
    """Ten users asking the same question must not cost ten copies."""
    payload = _payload("y" * 40_000)

    first = store_result(
        db_session, payload, _POLICY, catalog_slug="dedup", tool_name="echo"
    )
    db_session.commit()
    second = store_result(
        db_session, payload, _POLICY, catalog_slug="dedup", tool_name="echo"
    )
    db_session.commit()

    assert first is not None and second is not None
    stored_blob_ids.append(first.blob_id)

    assert first.blob_id == second.blob_id == content_hash(payload)
    assert first.file_id is None
    assert second.file_id is None


def test_result_past_the_ceiling_is_not_stored(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    policy = CachePolicySpec(inline_threshold_bytes=16, max_response_bytes=64)
    assert store_result(db_session, _payload("z" * 500), policy) is None
    db_session.rollback()


def test_canonical_bytes_ignore_key_order() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert canonical_bytes(left) == canonical_bytes(right)
    assert content_hash(left) == content_hash(right)


def test_digest_is_deterministic() -> None:
    payload = _payload("q" * 5_000)
    policy = CachePolicySpec()
    size = len(canonical_bytes(payload))
    assert build_digest(payload, policy, size_bytes=size) == build_digest(
        payload, policy, size_bytes=size
    )


def test_digest_stays_within_budget() -> None:
    payload = {
        "content": [{"type": "text", "text": "w" * 200_000}],
        "structuredContent": {
            f"field_{i}": {"nested": list(range(50))} for i in range(200)
        },
        "isError": False,
    }
    policy = CachePolicySpec(digest_max_bytes=2_048)
    digest = build_digest(payload, policy, size_bytes=len(canonical_bytes(payload)))
    assert len(canonical_bytes(digest)) <= 2_048


def test_digest_extracts_declared_paths() -> None:
    payload = _payload("hello")
    policy = CachePolicySpec(
        digest_paths=("structuredContent.items.0.name", "structuredContent.total")
    )
    digest = build_digest(payload, policy, size_bytes=len(canonical_bytes(payload)))
    assert digest["extracted"]["structuredContent.items.0.name"] == "Acme"
    assert digest["extracted"]["structuredContent.total"] == 1


def test_extract_path_returns_none_for_missing() -> None:
    payload = _payload("hello")
    assert extract_path(payload, "structuredContent.nope") is None
    assert extract_path(payload, "structuredContent.items.9") is None
    assert extract_path(payload, "isError.deeper") is None
