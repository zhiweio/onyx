"""MEMORY.md workspace hydration for craft sessions (P5).

The interactive path (``streaming.py``) refreshes ``MEMORY.md`` on the
same cadence as the recall preamble; ``write_memory_md_to_session`` is the
reconcile-side twin for long-lived sessions regaining a workspace after a
sandbox reset — it recalls against the session's most recent user message.

Both writers are strictly best-effort: a failure logs and the turn
proceeds without the file (memory is an enhancement, never a correctness
dependency).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from onyx.memory.long_term import (
    recall,
    render_memory_markdown,
    session_memory_scope,
)
from onyx.server.features.build.db.build_session import get_session_messages
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.utils.logger import setup_logger

logger = setup_logger()


def write_memory_md_to_session(
    db_session: Session,
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
) -> None:
    """Best-effort MEMORY.md refresh during session reconcile."""
    try:
        from onyx.db.models import BuildSession

        build_session = db_session.get(BuildSession, session_id)
        if build_session is None:
            return
        scope = session_memory_scope(db_session, build_session)
        if scope is None:
            return
        query = _last_user_message_text(db_session, session_id)
        if not query:
            return
        memories = recall(
            db_session,
            scope.user_id,
            query,
            project_id=scope.project_id,
        )
        if not memories:
            return
        sandbox_manager.write_sandbox_file(
            sandbox_id,
            f"sessions/{session_id}/MEMORY.md",
            render_memory_markdown(memories, scope.project_id),
        )
    except Exception:
        logger.exception("Failed to write MEMORY.md for session %s", session_id)


def _last_user_message_text(db_session: Session, session_id: UUID) -> str | None:
    from onyx.configs.constants import MessageType

    rows = get_session_messages(session_id=session_id, db_session=db_session)
    for message in reversed(rows):
        if message.type != MessageType.USER:
            continue
        meta = message.message_metadata or {}
        if not isinstance(meta, dict):
            continue
        content = (
            (meta.get("content") or {}) if isinstance(meta.get("content"), dict) else {}
        )
        text = content.get("text") or ""
        if isinstance(text, str) and text.strip():
            # Recall queries only need the gist; the preamble wrap keeps
            # injected recalled-memories markers out of the query.
            return text.strip()[:2000]
    return None
