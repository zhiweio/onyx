"""Audit report API: tool calls, approvals/quarantines, usage, query history.

One aggregation router over the existing persisted sources (plus the
new platform_tool_log). Query history reads SearchQuery when the
deployment enables recording; the page degrades gracefully when off.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import (
    ActionApproval,
    ContentQuarantine,
    SearchQuery,
    User,
    UserUsage,
)
from onyx.db.platform_tool_log import (
    count_tool_calls,
    list_tool_calls,
    tool_call_stats,
)

router = APIRouter(prefix="/admin/audit")


def _parse_when(value: str | None, *, days_default: int) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc) - timedelta(days=days_default)


@router.get("/tool-calls")
def audit_tool_calls(
    start: str | None = None,
    end: str | None = None,
    tool: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    start_at = _parse_when(start, days_default=7)
    end_at = _parse_when(end, days_default=36500) if end else None
    return {
        "items": list_tool_calls(
            db_session,
            start=start_at,
            end=end_at,
            tool=tool,
            q=q,
            limit=limit,
            offset=offset,
        ),
        "total_items": count_tool_calls(
            db_session, start=start_at, end=end_at, tool=tool, q=q
        ),
        "stats": tool_call_stats(db_session, start=start_at, end=end_at),
    }


@router.get("/approvals")
def audit_approvals(
    start: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    start_at = _parse_when(start, days_default=30)
    conditions = [ActionApproval.created_at >= start_at]
    if q:
        conditions.append(ActionApproval.app_name.ilike(f"%{q}%"))
    stmt = (
        select(ActionApproval)
        .where(*conditions)
        .order_by(ActionApproval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    total = db_session.scalar(
        select(func.count()).select_from(ActionApproval).where(*conditions)
    )
    rows = db_session.scalars(stmt).all()
    return {
        "items": [
            {
                "id": str(row.approval_id),
                "session_id": str(row.session_id),
                "app_name": row.app_name,
                "decision": row.decision.value if row.decision else None,
                "decided_at": row.decided_at.isoformat() if row.decided_at else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "total_items": int(total or 0),
    }


@router.get("/quarantines")
def audit_quarantines(
    start: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    start_at = _parse_when(start, days_default=30)
    conditions = [ContentQuarantine.created_at >= start_at]
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(
                ContentQuarantine.url_hash.ilike(pattern),
                ContentQuarantine.verdict.ilike(pattern),
            )
        )
    stmt = (
        select(ContentQuarantine)
        .where(*conditions)
        .order_by(ContentQuarantine.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    total = db_session.scalar(
        select(func.count()).select_from(ContentQuarantine).where(*conditions)
    )
    rows = db_session.scalars(stmt).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "session_id": str(row.session_id) if row.session_id else None,
                "url_hash": row.url_hash,
                "verdict": row.verdict,
                "decision": row.decision.value if row.decision else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "total_items": int(total or 0),
    }


@router.get("/usage")
def audit_usage(
    days: int = Query(default=30, le=365),
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    start_at = datetime.now(timezone.utc) - timedelta(days=days)
    queries = db_session.scalar(
        select(func.count())
        .select_from(SearchQuery)
        .where(SearchQuery.created_at >= start_at)
    )
    users = db_session.scalar(
        select(func.count(func.distinct(UserUsage.user_id))).where(
            UserUsage.window_start >= start_at
        )
    )
    from onyx.db.models import PlatformToolLog

    tool_calls = db_session.scalar(
        select(func.count())
        .select_from(PlatformToolLog)
        .where(PlatformToolLog.created_at >= start_at)
    )
    return {
        "days": days,
        "search_queries": int(queries or 0),
        "active_users": int(users or 0),
        "tool_calls": int(tool_calls or 0),
    }


@router.get("/query-history")
def audit_query_history(
    start: str | None = None,
    end: str | None = None,
    user_email: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Search query history (EE query-history replacement).

    Reads whatever the deployment records into SearchQuery; when
    recording is off the page shows an empty state rather than 500.
    """
    start_at = _parse_when(start, days_default=30)
    end_at = _parse_when(end, days_default=36500) if end else None

    stmt = select(SearchQuery, User.email).join(User, SearchQuery.user_id == User.id)
    count_stmt = (
        select(func.count())
        .select_from(SearchQuery)
        .join(User, SearchQuery.user_id == User.id)
    )
    if end_at:
        stmt = stmt.where(SearchQuery.created_at < end_at)
        count_stmt = count_stmt.where(SearchQuery.created_at < end_at)
    if start:
        stmt = stmt.where(SearchQuery.created_at >= start_at)
        count_stmt = count_stmt.where(SearchQuery.created_at >= start_at)
    if user_email:
        stmt = stmt.where(User.email == user_email)
        count_stmt = count_stmt.where(User.email == user_email)
    if q:
        pattern = f"%{q}%"
        fuzzy = or_(
            SearchQuery.query.ilike(pattern),
            User.email.ilike(pattern),
        )
        stmt = stmt.where(fuzzy)
        count_stmt = count_stmt.where(fuzzy)

    total = db_session.scalar(count_stmt) or 0
    rows = db_session.execute(
        stmt.order_by(SearchQuery.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "total_items": int(total),
        "items": [
            {
                "user": email,
                "query": row.query,
                "created_at": row.created_at.isoformat(),
            }
            for row, email in rows
        ],
    }
