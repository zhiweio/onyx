"""Persist MCP tool results in Iceberg. Redis still holds only a handle."""

import hashlib
import json
from typing import Any

from onyx.configs.app_configs import MCP_RESULT_MAX_BYTES
from onyx.db.enums import MCPResultStorage
from onyx.db.mcp_gateway import get_blob, upsert_blob__no_commit
from onyx.db.mcp_iceberg import append_result, blob_prefix_for, get_result
from onyx.mcp_gateway.digest import build_digest
from onyx.mcp_gateway.models import CachePolicySpec, StoredResult
from onyx.utils.logger import setup_logger

logger = setup_logger()


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def exceeds_ceiling(size_bytes: int, policy: CachePolicySpec) -> bool:
    """Whether a body is too large to persist at all."""
    return size_bytes > min(policy.max_response_bytes, MCP_RESULT_MAX_BYTES)


def _to_stored(record_payload: dict[str, Any], *, blob_id: str, size_bytes: int, digest: dict[str, Any]) -> StoredResult:
    return StoredResult(
        blob_id=blob_id,
        content_hash=blob_id,
        size_bytes=size_bytes,
        storage=MCPResultStorage.ICEBERG,
        digest=digest,
        file_id=None,
        payload=record_payload,
    )


def store_result(
    db_session: Any,
    payload: dict[str, Any],
    policy: CachePolicySpec,
    *,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
) -> StoredResult | None:
    """Write one result to Iceberg and a thin Postgres pointer."""
    raw = canonical_bytes(payload)
    size_bytes = len(raw)
    if exceeds_ceiling(size_bytes, policy):
        logger.info(
            "MCP result of %s bytes exceeds the storage ceiling; passing through",
            size_bytes,
        )
        return None

    blob_id = content_hash(payload)
    digest = build_digest(payload, policy, size_bytes=size_bytes)
    slug = catalog_slug or ""
    loaded = get_result(blob_id, catalog_slug=slug or None)
    if loaded is None:
        append_result(
            blob_id=blob_id,
            catalog_slug=slug,
            effective_tool_name=tool_name or "",
            payload=payload,
            digest=digest,
            size_bytes=size_bytes,
        )

    upsert_blob__no_commit(
        db_session,
        blob_id=blob_id,
        size_bytes=size_bytes,
        storage=MCPResultStorage.ICEBERG,
        digest=digest,
        inline_payload=None,
        file_id=None,
        provider_slug=catalog_slug,
        tool_name=tool_name,
    )

    return _to_stored(payload, blob_id=blob_id, size_bytes=size_bytes, digest=digest)


def load_result(
    db_session: Any, blob_id: str, *, with_payload: bool = True
) -> StoredResult | None:
    """Load a stored result from Iceberg. `with_payload=False` skips the body."""
    row = get_blob(db_session, blob_id)
    if row is None:
        return None
    payload: dict[str, Any] | None = None
    if with_payload:
        catalog_slug = row.provider_slug
        loaded = get_result(blob_id, catalog_slug=catalog_slug)
        if loaded is None:
            logger.warning("Iceberg result missing for blob %s", blob_id)
            return None
        payload = loaded.payload
    return StoredResult(
        blob_id=row.id,
        content_hash=row.id,
        size_bytes=row.size_bytes,
        storage=MCPResultStorage.ICEBERG,
        digest=row.digest,
        file_id=None,
        payload=payload,
    )


def delete_object(file_id: str) -> None:
    """Leftover hook. MCP results no longer live as file-store JSON objects."""
    logger.debug("Ignoring file-store delete for retired MCP object %s", file_id)


# Re-export for tests that imported codec helpers from this module.
__all__ = [
    "blob_prefix_for",
    "canonical_bytes",
    "content_hash",
    "delete_object",
    "exceeds_ceiling",
    "load_result",
    "store_result",
]
