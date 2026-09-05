"""Three-tier storage for MCP tool results.

MCP servers routinely answer with several megabytes. Putting that in Redis, in
a JSONB column, and in the model's context at once is what made the first
version fall over, so each tier now carries only what it is good at:

- **Redis** holds the digest and the handle. Always kilobytes, whatever the
  body weighs, so the hot path stays a single small round trip.
- **Postgres** holds the metadata row, and the body too when it is small
  enough that a separate object would cost more than it saves.
- **The file store** (MinIO/S3) holds large bodies, gzipped.

Bodies are keyed by the sha256 of their canonical JSON. The same answer
fetched by ten users is stored once, and re-fetching an unchanged answer
rewrites nothing.
"""

import gzip
import hashlib
import json
from io import BytesIO
from typing import Any

from onyx.configs.app_configs import MCP_RESULT_MAX_BYTES
from onyx.configs.constants import FileOrigin
from onyx.db.enums import MCPResultStorage
from onyx.db.mcp_gateway import get_blob, touch_blob__no_commit, upsert_blob__no_commit
from onyx.db.models import MCPResultBlob
from onyx.file_store.file_store import get_default_file_store
from onyx.mcp_gateway.digest import build_digest
from onyx.mcp_gateway.models import CachePolicySpec, StoredResult
from onyx.utils.logger import setup_logger

logger = setup_logger()

_FILE_ID_PREFIX = "mcp-result-"
_GZIP_LEVEL = 6


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Stable serialization used for both hashing and storage.

    Sorted keys and fixed separators mean an identical answer hashes
    identically regardless of how the upstream ordered its JSON.
    """
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def file_id_for(blob_id: str) -> str:
    return f"{_FILE_ID_PREFIX}{blob_id}"


def exceeds_ceiling(size_bytes: int, policy: CachePolicySpec) -> bool:
    """Whether a body is too large to persist at all."""
    return size_bytes > min(policy.max_response_bytes, MCP_RESULT_MAX_BYTES)


def _write_object(blob_id: str, raw: bytes) -> str:
    """Write the gzipped body to the file store, keyed by content hash.

    Idempotent: the same hash means the same bytes, so a second write for an
    existing object is skipped rather than repeated.
    """
    file_store = get_default_file_store()
    file_id = file_id_for(blob_id)
    if file_store.has_file(
        file_id=file_id,
        file_origin=FileOrigin.MCP_RESULT,
        file_type="application/gzip",
    ):
        return file_id

    compressed = gzip.compress(raw, compresslevel=_GZIP_LEVEL)
    file_store.save_file(
        file_id=file_id,
        content=BytesIO(compressed),
        display_name=file_id,
        file_origin=FileOrigin.MCP_RESULT,
        file_type="application/gzip",
        file_metadata={"content_type": "application/json", "encoding": "gzip"},
    )
    return file_id


def _read_object(file_id: str) -> dict[str, Any]:
    file_store = get_default_file_store()
    with file_store.read_file(file_id, mode="b", use_tempfile=True) as handle:
        raw = gzip.decompress(handle.read())
    parsed = json.loads(raw.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def store_result(
    db_session: Any,
    payload: dict[str, Any],
    policy: CachePolicySpec,
    *,
    catalog_slug: str | None = None,
    tool_name: str | None = None,
) -> StoredResult | None:
    """Persist one result and return its handle, or None if it is too large.

    Callers own the transaction; this flushes but does not commit.
    """
    raw = canonical_bytes(payload)
    size_bytes = len(raw)
    if exceeds_ceiling(size_bytes, policy):
        logger.info(
            "MCP result of %s bytes exceeds the storage ceiling; passing through",
            size_bytes,
        )
        return None

    blob_id = hashlib.sha256(raw).hexdigest()
    digest = build_digest(payload, policy, size_bytes=size_bytes)

    inline = size_bytes <= policy.inline_threshold_bytes
    storage = MCPResultStorage.INLINE if inline else MCPResultStorage.OBJECT
    file_id = None if inline else _write_object(blob_id, raw)

    upsert_blob__no_commit(
        db_session,
        blob_id=blob_id,
        size_bytes=size_bytes,
        storage=storage,
        digest=digest,
        inline_payload=payload if inline else None,
        file_id=file_id,
        provider_slug=catalog_slug,
        tool_name=tool_name,
    )

    return StoredResult(
        blob_id=blob_id,
        content_hash=blob_id,
        size_bytes=size_bytes,
        storage=storage,
        digest=digest,
        file_id=file_id,
        payload=payload,
    )


def load_result(
    db_session: Any, blob_id: str, *, with_payload: bool = True
) -> StoredResult | None:
    """Load a stored result. `with_payload=False` skips the object-store read."""
    row = get_blob(db_session, blob_id)
    if row is None:
        return None
    touch_blob__no_commit(db_session, blob_id)
    return _to_stored(row, with_payload=with_payload)


def _to_stored(row: MCPResultBlob, *, with_payload: bool) -> StoredResult:
    payload: dict[str, Any] | None = None
    if with_payload:
        if row.storage == MCPResultStorage.INLINE:
            payload = row.inline_payload or {}
        elif row.file_id:
            try:
                payload = _read_object(row.file_id)
            except Exception:
                # A missing object is recoverable: the caller refetches upstream.
                logger.exception("Could not read MCP result object for blob %s", row.id)
                payload = None
    return StoredResult(
        blob_id=row.id,
        content_hash=row.id,
        size_bytes=row.size_bytes,
        storage=row.storage,
        digest=row.digest,
        file_id=row.file_id,
        payload=payload,
    )


def delete_object(file_id: str) -> None:
    """Remove a body from the file store, tolerating an already-missing object."""
    try:
        get_default_file_store().delete_file(file_id, error_on_missing=False)
    except Exception:
        logger.exception("Could not delete MCP result object %s", file_id)
