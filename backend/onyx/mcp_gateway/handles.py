"""Who may read which stored MCP result.

A handle is the sha256 of the body, so it cannot be guessed without already
holding the content. That makes it safe by construction, but not sufficient: a
handle can end up in a prompt, and a model that repeats one should not be able
to read another user's result with it.

So a handle is also *granted*. The tool that produced a result records a grant
for the user who ran it; `mcp_result` refuses to read anything ungranted.
Grants expire on their own, since a conversation that still needs the body will
have re-read it in the meantime.
"""

from onyx.cache.factory import get_cache_backend
from onyx.cache.interface import CACHE_TRANSIENT_ERRORS
from onyx.utils.logger import setup_logger

logger = setup_logger()

_GRANT_PREFIX = "mcp_gateway:handle_grant:"
# Long enough to outlive a working session, short enough that a leaked handle
# stops being useful.
_GRANT_TTL_SECONDS = 24 * 3600


def _grant_key(user_id: str, blob_id: str) -> str:
    return f"{_GRANT_PREFIX}{user_id}:{blob_id}"


def grant_handle(user_id: str, blob_id: str) -> None:
    """Let this user read this result."""
    if not user_id or not blob_id:
        return
    try:
        get_cache_backend().set(
            _grant_key(user_id, blob_id), "1", ex=_GRANT_TTL_SECONDS
        )
    except CACHE_TRANSIENT_ERRORS:
        logger.debug("Could not record MCP result handle grant", exc_info=True)


def has_handle_grant(user_id: str, blob_id: str) -> bool:
    """Whether this user produced this result recently.

    Fails closed: if the cache cannot answer, the read is refused rather than
    allowed on an unverified handle.
    """
    if not user_id or not blob_id:
        return False
    try:
        return get_cache_backend().exists(_grant_key(user_id, blob_id))
    except CACHE_TRANSIENT_ERRORS:
        logger.warning("Could not verify MCP result handle grant", exc_info=True)
        return False
