"""Digest cache for the sandbox session config (``opencode.json``).

``reconcile_session_llm_config`` must verify the sandbox file each turn,
which costs a sandbox RPC. The digest cache lets it skip that read while
the inputs provably produced the last write. Any out-of-band config write
(restore, skills reload) must invalidate the digest so the next reconcile
re-reads the file as the source of truth.

The remember/known helpers take the caller's cache so reconcile keeps a
single backend resolution (and its tests keep patching one object).
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from onyx.cache.factory import get_cache_backend

_DIGEST_TTL_SECONDS = 7 * 24 * 3600


def config_digest_key(session_id: UUID) -> str:
    return f"craft:session_config_digest:{session_id}"


def digest_of_config(expected_config_json: str) -> str:
    return hashlib.sha256(expected_config_json.encode("utf-8")).hexdigest()


def remember_config_digest(
    session_id: UUID, expected_config_json: str, cache: Any
) -> None:
    """Record the digest of a config this host just verified or wrote."""
    cache.set(
        config_digest_key(session_id),
        digest_of_config(expected_config_json),
        ex=_DIGEST_TTL_SECONDS,
    )


def known_config_digest(session_id: UUID, cache: Any) -> str | None:
    value = cache.get(config_digest_key(session_id))
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else str(value)


def invalidate_config_digest(session_id: UUID) -> None:
    """Drop the digest after an out-of-band config write (pod restore,
    skills reload) whose exact content this cache cannot vouch for."""
    get_cache_backend().delete(config_digest_key(session_id))
