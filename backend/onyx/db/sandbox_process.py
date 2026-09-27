"""Host-side registry for background processes and their output watches.

The daemon owns the live handle and the log file; this module owns the
durable registry the agent's tool, the watch lane, and the reaper read.
Wakes reuse the interactive-turn machinery (the same path Craft's own
continuation uses), so a watch event lands in the session as a normal turn
subject to the session's budget and the lease/fence rules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.db.models import ProcessWatch, SandboxProcess

logger = logging.getLogger(__name__)

# watch fire throttle: one wake per watch per this window
WATCH_MIN_FIRE_INTERVAL_S = 60
WATCH_TTL_S = 24 * 60 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_process_registry(
    db_session: Session,
    *,
    process_id: str,
    sandbox_id: UUID,
    session_id: UUID | None,
    command_redacted: str,
    kind: str,
    expires_at: datetime,
) -> SandboxProcess:
    """Idempotent registry insert — a reattach (same daemon id) updates the
    expiry instead of stacking rows."""
    row = db_session.get(SandboxProcess, process_id)
    if row is None:
        row = SandboxProcess(
            process_id=process_id,
            sandbox_id=sandbox_id,
            session_id=session_id,
            command_redacted=command_redacted,
            kind=kind,
            expires_at=expires_at,
        )
        db_session.add(row)
    else:
        row.expires_at = expires_at
    db_session.flush()
    return row


def mark_process_status(
    db_session: Session,
    *,
    process_id: str,
    status: str,
    exit_code: int | None = None,
) -> None:
    row = db_session.get(SandboxProcess, process_id)
    if row is None:
        return
    row.status = status
    row.exit_code = exit_code
    db_session.flush()


def get_process_for_session(
    db_session: Session, *, process_id: str, session_id: UUID
) -> SandboxProcess | None:
    return db_session.scalar(
        select(SandboxProcess).where(
            SandboxProcess.process_id == process_id,
            SandboxProcess.session_id == session_id,
        )
    )


def list_running_processes_for_sandbox(
    db_session: Session, sandbox_id: UUID
) -> list[SandboxProcess]:
    return list(
        db_session.scalars(
            select(SandboxProcess).where(
                SandboxProcess.sandbox_id == sandbox_id,
                SandboxProcess.status == "running",
            )
        )
    )


def create_watch(
    db_session: Session,
    *,
    process_id: str,
    session_id: UUID,
    user_id: UUID,
    pattern: str,
    cursor: int,
    ttl_seconds: int = WATCH_TTL_S,
) -> ProcessWatch:
    watch = ProcessWatch(
        process_id=process_id,
        session_id=session_id,
        user_id=user_id,
        pattern=pattern,
        cursor=cursor,
        expires_at=_now() + timedelta(seconds=ttl_seconds),
    )
    db_session.add(watch)
    db_session.flush()
    return watch


def list_active_watches(db_session: Session) -> list[ProcessWatch]:
    """All watches whose process is still running and whose TTL is live."""
    return list(
        db_session.scalars(
            select(ProcessWatch)
            .join(
                SandboxProcess,
                SandboxProcess.process_id == ProcessWatch.process_id,
            )
            .where(SandboxProcess.status == "running")
            .where(
                (ProcessWatch.expires_at.is_(None))
                | (ProcessWatch.expires_at > _now())
            )
        )
    )


def delete_watch(db_session: Session, *, watch_id: UUID) -> None:
    db_session.execute(delete(ProcessWatch).where(ProcessWatch.id == watch_id))
    db_session.flush()


def is_wake_throttled(
    watch: ProcessWatch, *, min_fire_interval_s: int = WATCH_MIN_FIRE_INTERVAL_S
) -> bool:
    if watch.last_fired_at is None:
        return False
    return (
        _now() - watch.last_fired_at
    ).total_seconds() < min_fire_interval_s


def process_registry_snapshot(row: SandboxProcess) -> dict[str, Any]:
    """User-facing summary for the tool's list action."""
    return {
        "process_id": row.process_id,
        "kind": row.kind,
        "command": row.command_redacted,
        "status": row.status,
        "exit_code": row.exit_code,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def new_watch_event_envelope(
    *,
    process_id: str,
    event: str,
    matched_line: str | None,
) -> str:
    """Wake prompt shown to the agent when a watch fires (QM wake-envelope
    shape): event facts + explicit no-op guidance."""
    detail = matched_line or ""
    return (
        f"[Background process event] process {process_id}: {event}. "
        f"Matched output: {detail[:400]}. "
        "Read the process output if you need more, then continue the task. "
        "If there is nothing actionable, reply briefly instead of starting "
        "new work."
    )


def process_event_fire_key(watch_id: UUID, cursor: int) -> str:
    return f"watch:{watch_id}:{cursor}"
