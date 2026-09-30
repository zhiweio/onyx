"""Platform tool log DAL: journal writes + audit report queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from onyx.db.models import PlatformToolLog, User


def log_tool_call(
    db_session: Session,
    *,
    user_id: UUID,
    tool: str,
    arguments: dict[str, Any] | None = None,
    ok: bool = True,
    result_excerpt: str = "",
    duration_ms: int | None = None,
    session_id: UUID | None = None,
) -> None:
    """Append one journal row; never raises into the tool path."""
    try:
        db_session.add(
            PlatformToolLog(
                user_id=user_id,
                session_id=session_id,
                tool=tool[:128],
                arguments={
                    key: (value if len(str(value)) <= 512 else str(value)[:512])
                    for key, value in (arguments or {}).items()
                },
                ok=ok,
                result_excerpt=result_excerpt[:2000],
                duration_ms=duration_ms,
            )
        )
        db_session.commit()
    except Exception:
        db_session.rollback()


def _tool_call_conditions(
    *,
    start: datetime | None,
    end: datetime | None,
    user_id: UUID | None,
    tool: str | None,
    q: str | None,
) -> list[Any]:
    conditions: list[Any] = []
    if start is not None:
        conditions.append(PlatformToolLog.created_at >= start)
    if end is not None:
        conditions.append(PlatformToolLog.created_at < end)
    if user_id is not None:
        conditions.append(PlatformToolLog.user_id == user_id)
    if tool is not None:
        conditions.append(PlatformToolLog.tool == tool)
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(
                PlatformToolLog.tool.ilike(pattern),
                User.email.ilike(pattern),
                PlatformToolLog.result_excerpt.ilike(pattern),
            )
        )
    return conditions


def list_tool_calls(
    db_session: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    user_id: UUID | None = None,
    tool: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    stmt = select(PlatformToolLog, User.email).join(
        User, PlatformToolLog.user_id == User.id
    )
    stmt = stmt.where(
        *_tool_call_conditions(start=start, end=end, user_id=user_id, tool=tool, q=q)
    )
    stmt = stmt.order_by(PlatformToolLog.created_at.desc()).limit(limit).offset(offset)
    rows = db_session.execute(stmt).all()
    return [
        {
            "id": log.id,
            "user": email,
            "session_id": str(log.session_id) if log.session_id else None,
            "tool": log.tool,
            "arguments": log.arguments,
            "ok": log.ok,
            "result_excerpt": log.result_excerpt,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at.isoformat(),
        }
        for log, email in rows
    ]


def count_tool_calls(
    db_session: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    user_id: UUID | None = None,
    tool: str | None = None,
    q: str | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(PlatformToolLog)
        .join(User, PlatformToolLog.user_id == User.id)
    )
    stmt = stmt.where(
        *_tool_call_conditions(start=start, end=end, user_id=user_id, tool=tool, q=q)
    )
    return int(db_session.execute(stmt).scalar_one())


def tool_call_stats(
    db_session: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    stmt = select(
        PlatformToolLog.tool,
        func.count().label("calls"),
        func.sum(
            func.coalesce(
                # count ok=False without a bool-sum portability headache
                func.cast(~PlatformToolLog.ok, func.Integer()),
                0,
            )
        ).label("failures"),
        func.avg(PlatformToolLog.duration_ms).label("avg_ms"),
    ).group_by(PlatformToolLog.tool)
    if start is not None:
        stmt = stmt.where(PlatformToolLog.created_at >= start)
    if end is not None:
        stmt = stmt.where(PlatformToolLog.created_at < end)
    return [
        {
            "tool": tool,
            "calls": int(calls),
            "failures": int(failures or 0),
            "avg_ms": round(float(avg_ms), 1) if avg_ms is not None else None,
        }
        for tool, calls, failures, avg_ms in db_session.execute(stmt).all()
    ]
