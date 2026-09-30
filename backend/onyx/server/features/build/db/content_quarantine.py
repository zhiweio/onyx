"""Database operations for the content_quarantine table (WS6 release flow).

The sandbox-proxy writes quarantine rows (best-effort, fail-open); the
approvals API reads and decides them. PENDING rows are deduped per
(session, url_hash) by the writer, so repeated fetches of the same page
never stack cards or notifications.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    ContentQuarantineDecision,
    ContentReleaseScope,
)
from onyx.db.models import BuildSession, ContentQuarantine
from onyx.utils.logger import setup_logger

logger = setup_logger()


def upsert_pending_content_quarantine(
    db_session: Session,
    *,
    session_id: UUID,
    url_host: str,
    url_path: str,
    url_hash: str,
    verdict: str,
    patterns_matched: list[str],
    evidence_excerpt: str,
) -> tuple[ContentQuarantine, bool]:
    """Return the quarantine row for (session, url_hash) and whether it was
    just created. An existing PENDING row is returned untouched so the caller
    only announces/notifies on first sight."""
    existing = db_session.scalar(
        select(ContentQuarantine).where(
            ContentQuarantine.session_id == session_id,
            ContentQuarantine.url_hash == url_hash,
            ContentQuarantine.decision == ContentQuarantineDecision.PENDING,
        )
    )
    if existing is not None:
        return existing, False
    row = ContentQuarantine(
        session_id=session_id,
        url_host=url_host,
        url_path=url_path,
        url_hash=url_hash,
        verdict=verdict,
        patterns_matched=patterns_matched,
        evidence_excerpt=evidence_excerpt[:500],
        decision=ContentQuarantineDecision.PENDING,
    )
    db_session.add(row)
    db_session.flush()
    return row, True


def list_pending_content_quarantines(
    db_session: Session,
    session_id: UUID,
) -> list[ContentQuarantine]:
    """All undecided quarantines for a session — the /live feed for cards."""
    return list(
        db_session.scalars(
            select(ContentQuarantine)
            .where(ContentQuarantine.session_id == session_id)
            .where(ContentQuarantine.decision == ContentQuarantineDecision.PENDING)
            .order_by(ContentQuarantine.created_at.desc())
        )
    )


def get_content_quarantine_for_user(
    db_session: Session,
    quarantine_id: UUID,
    user_id: UUID,
) -> ContentQuarantine | None:
    """The quarantine row for one of the user's own sessions, else None."""
    return db_session.scalar(
        select(ContentQuarantine)
        .join(BuildSession, BuildSession.id == ContentQuarantine.session_id)
        .where(ContentQuarantine.id == quarantine_id)
        .where(BuildSession.user_id == user_id)
    )


def record_content_quarantine_decision(
    db_session: Session,
    *,
    quarantine: ContentQuarantine,
    decision: ContentQuarantineDecision,
    scope: ContentReleaseScope | None,
    decided_by: UUID,
) -> ContentQuarantine | None:
    """Record the human decision on a PENDING row. Returns the updated row,
    or None when a decision was already recorded (race loses silently)."""
    if quarantine.decision != ContentQuarantineDecision.PENDING:
        return None
    if decision is ContentQuarantineDecision.APPROVED and scope is None:
        raise ValueError("an approved release requires a scope")
    quarantine.decision = decision
    quarantine.scope = scope if decision is ContentQuarantineDecision.APPROVED else None
    quarantine.decided_by = decided_by
    quarantine.decided_at = datetime.now(timezone.utc)
    if (
        decision is ContentQuarantineDecision.APPROVED
        and scope is ContentReleaseScope.HOST
    ):
        quarantine.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    db_session.flush()
    return quarantine
