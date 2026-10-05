"""Verbatim harness event tape for craft sessions.

Rows are captured before lossy translation (``SandboxEventEnvelope``) and
form the session's harness-native history. Writes never raise into the
turn path: a tape failure logs and the turn continues — the tape is an
audit/replay asset, not a correctness dependency of the turn itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.db.models import CraftTapeEntry
from onyx.utils.logger import setup_logger

logger = setup_logger()

# 64KB per payload: plenty for a harness event, bounded for JSONB row cost.
TAPE_PAYLOAD_MAX_BYTES = 64 * 1024

TAPE_KINDS = ("harness_message", "context_event", "annotation")


def _clamp_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Truncate oversized payloads in place, marked, never dropped."""
    try:
        encoded = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return {"unserializable": True}
    if len(encoded.encode("utf-8")) <= TAPE_PAYLOAD_MAX_BYTES:
        return payload
    return {
        "truncated": True,
        "original_bytes": len(encoded.encode("utf-8")),
        "excerpt": encoded[:TAPE_PAYLOAD_MAX_BYTES],
    }


def append_tape_entry(
    db_session: Session,
    *,
    session_id: UUID | None,
    turn_index: int | None,
    kind: str,
    subtype: str,
    runtime: str,
    payload: dict[str, Any],
) -> None:
    """Append one verbatim entry. Caller commits; never raises."""
    try:
        db_session.add(
            CraftTapeEntry(
                session_id=session_id,
                turn_index=turn_index,
                kind=kind,
                subtype=subtype[:64],
                runtime=runtime[:32],
                payload=_clamp_payload(payload),
            )
        )
    except Exception:
        logger.warning("Tape append failed", exc_info=True)


def load_tape_entries(
    db_session: Session,
    session_id: UUID,
    *,
    kinds: list[str] | None = None,
    limit: int | None = None,
) -> list[CraftTapeEntry]:
    """Session tape in sequence order (oldest first)."""
    stmt = select(CraftTapeEntry).where(CraftTapeEntry.session_id == session_id)
    if kinds:
        stmt = stmt.where(CraftTapeEntry.kind.in_(kinds))
    stmt = stmt.order_by(CraftTapeEntry.id.asc())
    if limit is not None:
        stmt = stmt.order_by(CraftTapeEntry.id.desc()).limit(limit)
        rows = list(db_session.scalars(stmt))
        rows.reverse()
        return rows
    return list(db_session.scalars(stmt))


def prune_tape_before(db_session: Session, cutoff: datetime) -> int:
    """Delete tape rows older than the cutoff; returns the row count."""
    result = db_session.execute(
        delete(CraftTapeEntry).where(CraftTapeEntry.created_at < cutoff)
    )
    return int(
        getattr(result, "rowcount", 0) or 0
    )  # ods: ignore[getattr] - Result type varies


def tape_retention_cutoff(retention_days: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
