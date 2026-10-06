"""Admin API over the craft tape archive (PG hot window + Iceberg lake).

Mounted under ``/build/admin/tape`` (full admin panel access). Sessions
list from Postgres (``build_session`` is permanent metadata) decorated
with lake aggregates; events read lake-first with the Postgres tail past
the archive high-water mark appended, so a turn is whole regardless of
which tier holds it. Export streams canonical JSONL — one header line,
then one line per event — mirroring the dsh session-log export format.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import (
    CRAFT_TAPE_ARCHIVE_ENABLED,
    CRAFT_TAPE_HOT_RETENTION_DAYS,
    CRAFT_TAPE_ICEBERG_RETENTION_DAYS,
    CRAFT_TAPE_ICEBERG_SCHEMA_VERSION,
)
from onyx.db.craft_tape_archive import archived_high_water, tape_tail_events
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import BuildSession, CraftTapeArchiveBatch, CraftTapeEntry, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.tape_archive.pairing import analyze_pairings
from onyx.server.features.build.tape_archive.replay import ReplayPage

admin_router = APIRouter(prefix="/tape")

_DEFAULT_WINDOW_DAYS = 30
_MAX_PAGE = 100


def _lake_io() -> Any:
    from onyx.server.features.build.tape_archive.lake import io as lake_io

    return lake_io


def _parse_window(
    from_time: datetime | None, to_time: datetime | None
) -> tuple[datetime, datetime]:
    end = to_time or datetime.now(tz=timezone.utc)
    start = from_time or (end - timedelta(days=_DEFAULT_WINDOW_DAYS))
    return start, end


class TapeSessionItem(BaseModel):
    session_id: str
    name: str | None
    user_id: str | None
    user_email: str | None
    origin: str | None
    created_at: datetime | None
    turns: int
    events: int
    hot_events: int
    archived: bool
    input_tokens: int
    output_tokens: int
    cost: float
    last_activity: datetime | None
    last_reason: str | None
    runtimes: list[str]


class TapeSessionListResponse(BaseModel):
    items: list[TapeSessionItem]
    total: int


class TapeTurnItem(BaseModel):
    turn_index: int
    runtime: str
    started_at: datetime | None
    ended_at: datetime | None
    event_count: int
    input_tokens: int | None
    output_tokens: int | None
    cost: float | None
    turn_end_reason: str | None
    error_detail: str | None
    model: str | None
    tier: str  # "lake" | "hot" | "hot-open"


class TapeTurnListResponse(BaseModel):
    items: list[TapeTurnItem]
    total: int


class TapeEventItem(BaseModel):
    source_id: int
    turn_index: int | None
    kind: str
    subtype: str
    runtime: str
    payload: dict[str, Any]
    created_at: datetime
    annotations: list[str]


class TapeEventListResponse(BaseModel):
    items: list[TapeEventItem]
    next_source_id: int | None


class TapeStatsResponse(BaseModel):
    sessions: int
    turns: int
    events: int
    input_tokens: int
    output_tokens: int
    cost: float
    by_reason: dict[str, int]
    by_runtime: dict[str, int]
    archiving_enabled: bool
    hot_retention_days: int | None
    lake_retention_days: int | None


class TapeStatsSeriesResponse(BaseModel):
    series: list[dict[str, Any]]


def _hot_events_by_session(
    db_session: Session, session_ids: list[UUID], *, after_id: int
) -> dict[UUID, int]:
    if not session_ids:
        return {}
    stmt = (
        select(CraftTapeEntry.session_id, func.count())
        .where(
            CraftTapeEntry.session_id.in_(session_ids),
            CraftTapeEntry.id > after_id,
        )
        .group_by(CraftTapeEntry.session_id)
    )
    return {sid: int(count) for sid, count in db_session.execute(stmt) if sid}


_SORT_COLUMNS = {
    "created_at": BuildSession.created_at,
    "name": BuildSession.name,
    "last_activity": BuildSession.last_activity_at,
}


def _list_sessions_core(
    db_session: Session,
    *,
    start: datetime,
    end: datetime,
    origin: str | None,
    user_email: str | None,
    user_q: str | None,
    q: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
    owner_user_id: UUID | None,
) -> tuple[list[BuildSession], int]:
    """Shared session query for the admin and personal tape entries.

    ``owner_user_id`` hard-scopes to one user (personal entry); ``user_q``
    fuzzy-matches email or display name (admin entry). Sorting stays on
    Postgres columns; turn/event counts are lake aggregates and are not
    sortable server-side.
    """
    stmt = select(BuildSession).where(
        BuildSession.created_at >= start, BuildSession.created_at < end
    )
    if origin:
        stmt = stmt.where(BuildSession.origin == origin)
    if owner_user_id is not None:
        stmt = stmt.where(BuildSession.user_id == owner_user_id)
    if user_email:
        matching_users = list(
            db_session.scalars(
                select(User.id).where(  # ty: ignore[no-matching-overload]
                    User.email == user_email
                )
            )
        )
        stmt = stmt.where(BuildSession.user_id.in_(matching_users))
    if user_q:
        # User identities are emails in Onyx (the fastapi-users base table
        # carries no display-name column); match the address fuzzily.
        needle = f"%{user_q}%"
        matching_users = list(
            db_session.scalars(
                select(User.id).where(  # ty: ignore[no-matching-overload]
                    func.lower(User.email).like(func.lower(needle))
                )
            )
        )
        stmt = stmt.where(BuildSession.user_id.in_(matching_users))
    if q:
        stmt = stmt.where(
            func.lower(func.coalesce(BuildSession.name, "")).contains(q.lower())
        )

    total = db_session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = _SORT_COLUMNS.get(sort, BuildSession.created_at)
    ordered = column.desc() if order == "desc" else column.asc()
    rows = list(
        db_session.scalars(
            stmt.order_by(ordered.nulls_last()).offset(offset).limit(limit)
        )
    )
    return rows, int(total)


def _decorate_sessions(
    db_session: Session,
    rows: list[BuildSession],
    *,
    start: datetime,
    end: datetime,
) -> list[TapeSessionItem]:
    """Attach lake aggregates and hot-tail counts to a page of sessions."""
    page_ids = [row.id for row in rows]
    aggregates: dict[str, Any] = {}
    hot_after = 0
    if CRAFT_TAPE_ARCHIVE_ENABLED:
        hot_after = archived_high_water(db_session)
        aggregates = _lake_io().session_aggregates(
            from_time=start, to_time=end, session_ids=[str(sid) for sid in page_ids]
        )
    hot_counts = _hot_events_by_session(db_session, page_ids, after_id=hot_after)

    emails: dict[UUID, str] = {}
    user_ids = [row.user_id for row in rows if row.user_id is not None]
    if user_ids:
        # Column select, not a User entity load: the User model carries
        # joined-eager collection relationships (oauth_accounts), which
        # would force a .unique() on the Result here.
        # ty: ignore[unresolved-attribute] — Mapped[UUID] column, ty misses .in_
        for user_id, email in db_session.execute(
            select(User.id, User.email).where(User.id.in_(user_ids))
        ):
            emails[user_id] = email

    items = []
    for row in rows:
        agg = aggregates.get(str(row.id))
        hot = hot_counts.get(row.id, 0)
        items.append(
            TapeSessionItem(
                session_id=str(row.id),
                name=row.name,
                user_id=str(row.user_id) if row.user_id else None,
                user_email=emails.get(row.user_id) if row.user_id else None,
                origin=row.origin.value if row.origin is not None else None,
                created_at=row.created_at,
                turns=agg.turns if agg else 0,
                events=(agg.events if agg else 0) + hot,
                hot_events=hot,
                archived=agg is not None,
                input_tokens=agg.input_tokens if agg else 0,
                output_tokens=agg.output_tokens if agg else 0,
                cost=agg.cost if agg else 0.0,
                last_activity=agg.last_activity if agg else None,
                last_reason=agg.last_reason if agg else None,
                runtimes=list(agg.runtimes) if agg else [],
            )
        )
    return items


@admin_router.get("/sessions")
def list_tape_sessions(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    origin: str | None = None,
    user_email: str | None = None,
    user_q: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeSessionListResponse:
    """Browse every tenant craft session with tape aggregates."""
    limit = min(limit, _MAX_PAGE)
    start, end = _parse_window(from_time, to_time)
    rows, total = _list_sessions_core(
        db_session,
        start=start,
        end=end,
        origin=origin,
        user_email=user_email,
        user_q=user_q,
        q=q,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
        owner_user_id=None,
    )
    items = _decorate_sessions(db_session, rows, start=start, end=end)
    return TapeSessionListResponse(items=items, total=total)


def _merged_events(
    db_session: Session,
    session_id: UUID,
    *,
    after_source_id: int | None,
    limit: int,
) -> list[TapeEventItem]:
    """Lake events plus the Postgres tail past the high-water mark."""
    from onyx.server.features.build.tape_archive.reader import merged_tape_events

    ordered = merged_tape_events(
        db_session, session_id, after_source_id=after_source_id, limit=limit
    )
    pairings = analyze_pairings(_EventView.list_of(ordered))
    items = [
        TapeEventItem(
            **event,
            annotations=pairings.annotations_for(event["source_id"]),
        )
        for event in ordered
    ]
    return items


class _EventView:
    """Duck-typed accessor so pairing works over plain dicts."""

    __slots__ = ("source_id", "kind", "subtype", "payload")

    def __init__(self, event: dict[str, Any]) -> None:
        self.source_id = event["source_id"]
        self.kind = event["kind"]
        self.subtype = event["subtype"]
        self.payload = event["payload"]

    @classmethod
    def list_of(cls, events: list[dict[str, Any]]) -> list[_EventView]:
        return [cls(event) for event in events]


def _tape_events_response(
    db_session: Session,
    session_id: UUID,
    *,
    after_source_id: int | None,
    limit: int,
) -> TapeEventListResponse:
    """One session's tape, ascending by source_id (cursor paginated)."""
    items = _merged_events(
        db_session, session_id, after_source_id=after_source_id, limit=limit
    )
    next_source_id = items[-1].source_id if len(items) >= limit else None
    return TapeEventListResponse(items=items, next_source_id=next_source_id)


@admin_router.get("/sessions/{session_id}/events")
def list_tape_events(
    session_id: UUID,
    after_source_id: int | None = None,
    limit: int = 200,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeEventListResponse:
    return _tape_events_response(
        db_session, session_id, after_source_id=after_source_id, limit=limit
    )


@admin_router.get("/sessions/{session_id}/turns")
def list_tape_turns(
    session_id: UUID,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeTurnListResponse:
    return _tape_turns_response(db_session, session_id)


def _tape_turns_response(db_session: Session, session_id: UUID) -> TapeTurnListResponse:
    """Turn summaries: archived lake turns plus open hot-window turns."""
    turns: dict[int, TapeTurnItem] = {}
    if CRAFT_TAPE_ARCHIVE_ENABLED:
        for record in _lake_io().load_turns(str(session_id)):
            turns[record.turn_index] = TapeTurnItem(
                turn_index=record.turn_index,
                runtime=record.runtime,
                started_at=record.started_at,
                ended_at=record.ended_at,
                event_count=record.event_count,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost=record.cost,
                turn_end_reason=record.turn_end_reason,
                error_detail=record.error_detail,
                model=record.model,
                tier="lake",
            )
    high_water = archived_high_water(db_session) if CRAFT_TAPE_ARCHIVE_ENABLED else 0
    hot_rows = tape_tail_events(db_session, session_id, after_id=high_water, limit=5000)
    by_turn: dict[int, list[CraftTapeEntry]] = {}
    for row in hot_rows:
        by_turn.setdefault(
            row.turn_index if row.turn_index is not None else -1, []
        ).append(row)
    for turn_index, rows in by_turn.items():
        if turn_index in turns:
            # Partially archived turn: its tail still lives in Postgres.
            existing = turns[turn_index]
            existing.event_count += len(rows)
            continue
        started = None
        ended = None
        reason = None
        detail = None
        model = None
        for row in rows:
            if row.kind == "context_event" and row.subtype == "turn/start":
                started = row.created_at
                model = (row.payload or {}).get("request_env", {}).get("model")
            elif row.kind == "context_event" and row.subtype == "turn/end":
                ended = row.created_at
                reason = (row.payload or {}).get("reason")
                detail = (row.payload or {}).get("detail")
        runtimes = [row.runtime for row in rows if row.runtime]
        turns[turn_index] = TapeTurnItem(
            turn_index=turn_index,
            runtime=runtimes[-1] if runtimes else "unknown",
            started_at=started or (min(r.created_at for r in rows) if rows else None),
            ended_at=ended,
            event_count=len(rows),
            input_tokens=None,
            output_tokens=None,
            cost=None,
            turn_end_reason=reason,
            error_detail=detail,
            model=model,
            tier="hot",
        )
    items = [turns[key] for key in sorted(turns)]
    return TapeTurnListResponse(items=items, total=len(items))


@admin_router.get("/events/window")
def tape_event_window(
    session_id: UUID,
    source_id: int,
    before: int = 20,
    after: int = 20,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeEventListResponse:
    """One event plus its raw log neighbors (dsh session-query readEvent)."""
    events = _merged_events(db_session, session_id, after_source_id=None, limit=500)
    index = next(
        (i for i, item in enumerate(events) if item.source_id == source_id), None
    )
    if index is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Tape event not found")
    lo = max(0, index - before)
    hi = min(len(events), index + after + 1)
    return TapeEventListResponse(items=events[lo:hi], next_source_id=None)


@admin_router.get("/stats")
def tape_stats(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeStatsResponse:
    start, end = _parse_window(from_time, to_time)
    if not CRAFT_TAPE_ARCHIVE_ENABLED:
        return TapeStatsResponse(
            sessions=0,
            turns=0,
            events=0,
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            by_reason={},
            by_runtime={},
            archiving_enabled=False,
            hot_retention_days=None,
            lake_retention_days=None,
        )
    stats = _lake_io().stats_windowed(from_time=start, to_time=end)
    return TapeStatsResponse(
        **stats,
        archiving_enabled=True,
        hot_retention_days=CRAFT_TAPE_HOT_RETENTION_DAYS or None,
        lake_retention_days=CRAFT_TAPE_ICEBERG_RETENTION_DAYS or None,
    )


@admin_router.get("/stats/series")
def tape_stats_series(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> TapeStatsSeriesResponse:
    start, end = _parse_window(from_time, to_time)
    if not CRAFT_TAPE_ARCHIVE_ENABLED:
        return TapeStatsSeriesResponse(series=[])
    return TapeStatsSeriesResponse(
        series=_lake_io().stats_series(from_time=start, to_time=end)
    )


def _export_lines(db_session: Session, session: BuildSession) -> Iterator[str]:
    """Canonical JSONL: header line, then one line per event (dsh format)."""
    header = {
        "type": "header",
        "schema_version": CRAFT_TAPE_ICEBERG_SCHEMA_VERSION,
        "session": {
            "id": str(session.id),
            "name": session.name,
            "origin": session.origin.value if session.origin is not None else None,
            "agent_provider": session.agent_provider,
            "agent_model": session.agent_model,
            "reasoning_effort": (
                session.reasoning_effort.value
                if session.reasoning_effort is not None
                else None
            ),
            "created_at": session.created_at.isoformat(),
        },
    }
    yield json.dumps(header, ensure_ascii=False, default=str) + "\n"
    cursor: int | None = None
    while True:
        items = _merged_events(
            db_session, session.id, after_source_id=cursor, limit=200
        )
        if not items:
            break
        for item in items:
            yield (
                json.dumps(
                    {
                        "type": "event",
                        "source_id": item.source_id,
                        "turn_index": item.turn_index,
                        "kind": item.kind,
                        "subtype": item.subtype,
                        "runtime": item.runtime,
                        "payload": item.payload,
                        "created_at": item.created_at.isoformat(),
                    },
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
        cursor = items[-1].source_id
        if len(items) < 200:
            break


@admin_router.get("/sessions/{session_id}/export")
def export_tape_session(
    session_id: UUID,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> StreamingResponse:
    session = db_session.scalar(
        select(BuildSession).where(BuildSession.id == session_id)
    )
    if session is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Build session not found")
    filename = f"craft-tape-{session_id}.jsonl"
    return StreamingResponse(
        _export_lines(db_session, session),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class HistoryClearRequest(BaseModel):
    confirm: bool = False


@admin_router.post("/history/clear")
def clear_tape_history(
    request: HistoryClearRequest,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> dict[str, int]:
    """Drop all tape facts for this tenant: lake, Postgres hot window, ledger."""
    if not request.confirm:
        raise OnyxError(OnyxErrorCode.BAD_REQUEST, "confirm=true is required")
    if CRAFT_TAPE_ARCHIVE_ENABLED:
        _lake_io().clear_tenant_tape()
    result = db_session.execute(delete(CraftTapeEntry))
    hot = (
        getattr(  # ods: ignore[getattr] - Result type varies
            result, "rowcount", 0
        )
        or 0
    )
    db_session.execute(delete(CraftTapeArchiveBatch))
    db_session.commit()
    return {"removed_hot_rows": int(hot)}


@admin_router.get("/sessions/{session_id}/replay")
def replay_tape_session(
    session_id: UUID,
    after_source_id: int | None = None,
    turn_index: int | None = None,
    limit: int = 400,
    db_session: Session = Depends(get_session),
    _: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
) -> ReplayPage:
    """Replay packets (live wire format) for cinematic playback."""
    from onyx.server.features.build.tape_archive.replay import build_replay_packets

    return build_replay_packets(
        db_session,
        session_id,
        after_source_id=after_source_id,
        turn_index=turn_index,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Personal entry: a user reads only their own sessions' tapes.
# ---------------------------------------------------------------------------

user_router = APIRouter(prefix="/tape")


def _require_owned_session(
    db_session: Session, session_id: UUID, user: User
) -> BuildSession:
    """Resolve a build session the caller owns; 404 hides foreign sessions."""
    session = db_session.scalar(
        select(BuildSession).where(BuildSession.id == session_id)
    )
    if session is None or session.user_id != user.id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Build session not found")
    return session


@user_router.get("/sessions")
def list_my_tape_sessions(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    origin: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> TapeSessionListResponse:
    """The caller's own craft sessions with tape aggregates."""
    limit = min(limit, _MAX_PAGE)
    start, end = _parse_window(from_time, to_time)
    rows, total = _list_sessions_core(
        db_session,
        start=start,
        end=end,
        origin=origin,
        user_email=None,
        user_q=None,
        q=q,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
        owner_user_id=user.id,
    )
    items = _decorate_sessions(db_session, rows, start=start, end=end)
    return TapeSessionListResponse(items=items, total=total)


@user_router.get("/sessions/{session_id}/turns")
def list_my_tape_turns(
    session_id: UUID,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> TapeTurnListResponse:
    _require_owned_session(db_session, session_id, user)
    return _tape_turns_response(db_session, session_id)


@user_router.get("/sessions/{session_id}/events")
def list_my_tape_events(
    session_id: UUID,
    after_source_id: int | None = None,
    limit: int = 200,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> TapeEventListResponse:
    _require_owned_session(db_session, session_id, user)
    return _tape_events_response(
        db_session, session_id, after_source_id=after_source_id, limit=limit
    )


@user_router.get("/sessions/{session_id}/replay")
def replay_my_tape_session(
    session_id: UUID,
    after_source_id: int | None = None,
    turn_index: int | None = None,
    limit: int = 400,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> ReplayPage:
    from onyx.server.features.build.tape_archive.replay import build_replay_packets

    _require_owned_session(db_session, session_id, user)
    return build_replay_packets(
        db_session,
        session_id,
        after_source_id=after_source_id,
        turn_index=turn_index,
        limit=limit,
    )


@user_router.get("/sessions/{session_id}/export")
def export_my_tape_session(
    session_id: UUID,
    db_session: Session = Depends(get_session),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
) -> StreamingResponse:
    session = _require_owned_session(db_session, session_id, user)
    filename = f"craft-tape-{session_id}.jsonl"
    return StreamingResponse(
        _export_lines(db_session, session),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
