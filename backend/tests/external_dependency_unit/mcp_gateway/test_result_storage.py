"""Storage tiering, content-hash dedup, and digest determinism.

These need Postgres and the file store, so they are external-dependency tests
rather than unit tests.
"""

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import MCPResultStorage
from onyx.db.mcp_gateway import delete_blobs
from onyx.file_store.file_store import get_default_file_store
from onyx.mcp_gateway.digest import build_digest, extract_path
from onyx.mcp_gateway.models import CachePolicySpec
from onyx.mcp_gateway.storage import (
    canonical_bytes,
    content_hash,
    load_result,
    store_result,
)

_INLINE_POLICY = CachePolicySpec(inline_threshold_bytes=32_768)
_SPILL_POLICY = CachePolicySpec(inline_threshold_bytes=1_024)


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
        for blob_id in created:
            file_store = get_default_file_store()
            try:
                file_store.delete_file(f"mcp-result-{blob_id}", error_on_missing=False)
            except Exception:
                pass
        delete_blobs(db_session, created)


def test_small_result_stays_inline(
    db_session: Session,
    stored_blob_ids: list[str],
    tenant_context: None,  # noqa: ARG001
) -> None:
    stored = store_result(db_session, _payload("small"), _INLINE_POLICY)
    db_session.commit()
    assert stored is not None
    stored_blob_ids.append(stored.blob_id)

    assert stored.storage == MCPResultStorage.INLINE
    assert stored.file_id is None

    loaded = load_result(db_session, stored.blob_id)
    db_session.commit()
    assert loaded is not None
    assert loaded.payload == _payload("small")


def test_large_result_spills_to_the_file_store(
    db_session: Session,
    stored_blob_ids: list[str],
    tenant_context: None,  # noqa: ARG001
) -> None:
    payload = _payload("x" * 50_000)
    stored = store_result(db_session, payload, _SPILL_POLICY)
    db_session.commit()
    assert stored is not None
    stored_blob_ids.append(stored.blob_id)

    assert stored.storage == MCPResultStorage.OBJECT
    assert stored.file_id == f"mcp-result-{stored.blob_id}"

    # It must survive a round trip through the object store unchanged.
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

    first = store_result(db_session, payload, _SPILL_POLICY)
    db_session.commit()
    second = store_result(db_session, payload, _SPILL_POLICY)
    db_session.commit()

    assert first is not None and second is not None
    stored_blob_ids.append(first.blob_id)

    assert first.blob_id == second.blob_id == content_hash(payload)
    assert first.file_id == second.file_id


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
