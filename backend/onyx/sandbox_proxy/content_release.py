"""Release grants + original-body stash for quarantined inbound content.

The WS6 enforce-mode screener stashes the original response body here when it
quarantines, so an approved release can serve the exact content the agent
asked for without re-fetching (the upstream may 403 the retry or drift).
Grants are Redis keys keyed by the URL hash; the ``content_quarantine`` row
is the durable audit source.

Scopes:
* ``once``    — consumed by the first matching fetch (atomic GET+DEL).
* ``session`` — covers one craft session for its lifetime (24h TTL).
* ``host``    — covers any session for 30 days (sliding TTL).
"""

from __future__ import annotations

import hashlib
import uuid

from onyx.cache.interface import CacheBackend
from onyx.db.enums import ContentReleaseScope

STASH_TTL_S = 60 * 60  # 1h — long enough for a human to review
ONCE_GRANT_TTL_S = 60 * 60
SESSION_GRANT_TTL_S = 24 * 60 * 60
HOST_GRANT_TTL_S = 30 * 24 * 60 * 60

_STASH_PREFIX = "content-stash"
_RELEASE_PREFIX = "content-release"


def url_hash_of(url: str) -> str:
    """SHA256 of the full request URL — grants and stash key off this."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _stash_key(url_hash: str) -> str:
    return f"{_STASH_PREFIX}:{url_hash}"


def _once_key(url_hash: str) -> str:
    return f"{_RELEASE_PREFIX}:once:{url_hash}"


def _session_key(url_hash: str, session_id: uuid.UUID) -> str:
    return f"{_RELEASE_PREFIX}:session:{session_id}:{url_hash}"


def _host_key(url_hash: str) -> str:
    return f"{_RELEASE_PREFIX}:host:{url_hash}"


def stash_body(url_hash: str, body: bytes, cache: CacheBackend) -> None:
    """Keep the original body so an approved release can serve it verbatim."""
    cache.set(_stash_key(url_hash), body, ex=STASH_TTL_S)


def load_stash(url_hash: str, cache: CacheBackend) -> bytes | None:
    raw = cache.get(_stash_key(url_hash))
    if raw is None:
        return None
    return raw if isinstance(raw, bytes) else str(raw).encode()


def grant_release(
    url_hash: str,
    scope: ContentReleaseScope,
    session_id: uuid.UUID | None,
    cache: CacheBackend,
) -> None:
    """Record an approved release. ``session`` requires the session id."""
    if scope is ContentReleaseScope.ONCE:
        cache.set(_once_key(url_hash), "1", ex=ONCE_GRANT_TTL_S)
    elif scope is ContentReleaseScope.SESSION:
        if session_id is None:
            raise ValueError("session-scope release requires a session id")
        cache.set(_session_key(url_hash, session_id), "1", ex=SESSION_GRANT_TTL_S)
    else:
        cache.set(_host_key(url_hash), "1", ex=HOST_GRANT_TTL_S)


def consume_release(
    url_hash: str,
    session_id: uuid.UUID | None,
    cache: CacheBackend,
) -> bool:
    """Return True (and consume ``once`` grants) when a release covers this
    fetch. Checked before screening, so released content never re-screens."""
    # once: GETDEL is the consumption — a lost race means another fetch took it.
    if cache.getdel(_once_key(url_hash)) is not None:
        return True
    if session_id is not None and cache.get(_session_key(url_hash, session_id)):
        return True
    return cache.get(_host_key(url_hash)) is not None


def revoke_release(
    url_hash: str, session_id: uuid.UUID | None, cache: CacheBackend
) -> None:
    """Revoke every live grant for the URL (admin action)."""
    cache.delete(_once_key(url_hash))
    cache.delete(_host_key(url_hash))
    if session_id is not None:
        cache.delete(_session_key(url_hash, session_id))
