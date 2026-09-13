"""Database operations for Craft long jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import (
    CraftJob,
    CraftJobCheckpoint,
    CraftJobEvent,
    CraftJobSpecialist,
)

OPEN_JOB_STATUSES = (
    CraftJobStatus.PENDING,
    CraftJobStatus.RUNNING,
    CraftJobStatus.WAITING_SPECIALISTS,
    CraftJobStatus.WAITING_LANES,
    CraftJobStatus.INTERRUPTED,
)

TERMINAL_JOB_STATUSES = (
    CraftJobStatus.SUCCEEDED,
    CraftJobStatus.FAILED,
    CraftJobStatus.CANCELLED,
)


def get_craft_job(db_session: Session, job_id: UUID) -> CraftJob | None:
    return db_session.scalar(
        select(CraftJob)
        .options(selectinload(CraftJob.specialists), selectinload(CraftJob.events))
        .where(CraftJob.id == job_id)
    )


def get_craft_job_for_user(
    db_session: Session, job_id: UUID, user_id: UUID
) -> CraftJob | None:
    job = get_craft_job(db_session, job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


def get_open_job_for_session(db_session: Session, session_id: UUID) -> CraftJob | None:
    return db_session.scalar(
        select(CraftJob)
        .options(selectinload(CraftJob.specialists), selectinload(CraftJob.events))
        .where(
            CraftJob.session_id == session_id,
            CraftJob.status.in_(OPEN_JOB_STATUSES),
        )
        .order_by(CraftJob.created_at.desc())
        .limit(1)
    )


def get_latest_job_for_session(
    db_session: Session, session_id: UUID
) -> CraftJob | None:
    return db_session.scalar(
        select(CraftJob)
        .options(selectinload(CraftJob.specialists), selectinload(CraftJob.events))
        .where(CraftJob.session_id == session_id)
        .order_by(CraftJob.created_at.desc())
        .limit(1)
    )


def latest_job_statuses_for_sessions(
    db_session: Session, session_ids: list[UUID]
) -> dict[UUID, CraftJobStatus]:
    """Return the newest job status for each parent session."""
    if not session_ids:
        return {}
    ranked = (
        select(
            CraftJob.session_id,
            CraftJob.status,
            func.row_number()
            .over(
                partition_by=CraftJob.session_id,
                order_by=(CraftJob.created_at.desc(), CraftJob.id.desc()),
            )
            .label("rn"),
        )
        .where(CraftJob.session_id.in_(session_ids))
        .subquery()
    )
    rows = db_session.execute(
        select(ranked.c.session_id, ranked.c.status).where(ranked.c.rn == 1)
    ).all()
    return {session_id: status for session_id, status in rows}


def get_specialist_for_session(
    db_session: Session, session_id: UUID
) -> CraftJobSpecialist | None:
    return db_session.scalar(
        select(CraftJobSpecialist)
        .options(selectinload(CraftJobSpecialist.job))
        .where(CraftJobSpecialist.session_id == session_id)
    )


def session_has_open_craft_job(db_session: Session, session_id: UUID) -> bool:
    """True if this session is a job parent or a specialist child."""
    if get_open_job_for_session(db_session, session_id) is not None:
        return True
    specialist = get_specialist_for_session(db_session, session_id)
    if specialist is None:
        return False
    job = specialist.job
    if job is None:
        return False
    return job.status in OPEN_JOB_STATUSES


def user_has_open_craft_job(db_session: Session, user_id: UUID) -> bool:
    return (
        db_session.scalar(
            select(CraftJob.id)
            .where(
                CraftJob.user_id == user_id,
                CraftJob.status.in_(OPEN_JOB_STATUSES),
            )
            .limit(1)
        )
        is not None
    )


def project_has_craft_job(db_session: Session, project_id: UUID) -> bool:
    return (
        db_session.scalar(
            select(CraftJob.id).where(CraftJob.project_id == project_id).limit(1)
        )
        is not None
    )


def create_craft_job(
    db_session: Session,
    *,
    user_id: UUID,
    session_id: UUID,
    name: str,
    domain: str,
    total_budget_seconds: int,
    phase_budget_seconds: int,
    project_id: UUID | None = None,
    scenario_id: UUID | None = None,
    phases: list[dict],
    state: dict[str, Any] | None = None,
) -> CraftJob:
    job = CraftJob(
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        scenario_id=scenario_id,
        name=name[:256],
        domain=domain,
        status=CraftJobStatus.PENDING,
        phases=phases,
        current_phase_index=0,
        state=state or {},
        total_budget_seconds=total_budget_seconds,
        phase_budget_seconds=phase_budget_seconds,
    )
    db_session.add(job)
    db_session.flush()
    return job


def mark_job_running(job: CraftJob) -> None:
    now = datetime.now(timezone.utc)
    job.status = CraftJobStatus.RUNNING
    if job.started_at is None:
        job.started_at = now
    _set_phase_status(job, job.current_phase_index, "running")


def mark_job_waiting_specialists(job: CraftJob) -> None:
    job.status = CraftJobStatus.WAITING_SPECIALISTS


def job_is_terminal(job: CraftJob) -> bool:
    return job.status in TERMINAL_JOB_STATUSES


def mark_job_cancelled(job: CraftJob) -> None:
    """Finish the job and stop every open specialist lane."""
    mark_job_finished(job, status=CraftJobStatus.CANCELLED)
    for specialist in job.specialists:
        if specialist.status in (
            CraftJobSpecialistStatus.PENDING,
            CraftJobSpecialistStatus.RUNNING,
        ):
            mark_specialist_finished(
                specialist,
                status=CraftJobSpecialistStatus.FAILED,
                error_detail="Cancelled",
            )


def mark_job_finished(
    job: CraftJob,
    *,
    status: CraftJobStatus,
    error_detail: str | None = None,
) -> None:
    job.status = status
    job.error_detail = error_detail
    job.finished_at = datetime.now(timezone.utc)
    if status == CraftJobStatus.SUCCEEDED:
        _set_phase_status(job, job.current_phase_index, "succeeded")


def advance_job_phase(job: CraftJob, next_index: int) -> None:
    _set_phase_status(job, job.current_phase_index, "succeeded")
    job.current_phase_index = next_index
    if next_index < len(job.phases):
        _set_phase_status(job, next_index, "running")
        job.status = CraftJobStatus.RUNNING


def job_elapsed_seconds(job: CraftJob, *, now: datetime | None = None) -> float:
    """Wall time minus HITL pause. Pause lives on ``job.state``."""
    if job.started_at is None:
        return 0.0
    started = job.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    clock = now or datetime.now(timezone.utc)
    elapsed = (clock - started).total_seconds()
    raw = job.state if isinstance(job.state, dict) else {}
    paused = float(raw.get("paused_seconds") or 0)
    pause_started = raw.get("pause_started_at")
    if isinstance(pause_started, str) and pause_started:
        try:
            pause_at = datetime.fromisoformat(pause_started)
        except ValueError:
            pause_at = None
        if pause_at is not None:
            if pause_at.tzinfo is None:
                pause_at = pause_at.replace(tzinfo=timezone.utc)
            paused += max(0.0, (clock - pause_at).total_seconds())
    return max(0.0, elapsed - paused)


def job_total_budget_exhausted(job: CraftJob) -> bool:
    return job_elapsed_seconds(job) >= job.total_budget_seconds


def add_specialist(
    db_session: Session,
    *,
    job: CraftJob,
    session_id: UUID,
    role: str,
    prompt: str,
    node_id: str | None = None,
    checkpoint_ns: str | None = None,
    input_digest: str | None = None,
    output_artifact_ids: list[str] | None = None,
) -> CraftJobSpecialist:
    row = CraftJobSpecialist(
        job_id=job.id,
        session_id=session_id,
        role=role[:64],
        prompt=prompt,
        node_id=node_id,
        checkpoint_ns=checkpoint_ns,
        input_digest=input_digest,
        output_artifact_ids=output_artifact_ids or [],
        status=CraftJobSpecialistStatus.RUNNING,
    )
    db_session.add(row)
    db_session.flush()
    return row


def mark_specialist_finished(
    specialist: CraftJobSpecialist,
    *,
    status: CraftJobSpecialistStatus,
    error_detail: str | None = None,
    output_artifact_ids: list[str] | None = None,
) -> None:
    specialist.status = status
    specialist.error_detail = error_detail
    specialist.finished_at = datetime.now(timezone.utc)
    if output_artifact_ids is not None:
        specialist.output_artifact_ids = output_artifact_ids


def specialists_all_terminal(job: CraftJob) -> bool:
    if not job.specialists:
        return True
    return all(
        row.status
        in (CraftJobSpecialistStatus.SUCCEEDED, CraftJobSpecialistStatus.FAILED)
        for row in job.specialists
    )


def specialists_any_failed(job: CraftJob) -> bool:
    return any(row.status == CraftJobSpecialistStatus.FAILED for row in job.specialists)


def count_open_specialists(job: CraftJob) -> int:
    return sum(
        1
        for row in job.specialists
        if row.status
        in (CraftJobSpecialistStatus.PENDING, CraftJobSpecialistStatus.RUNNING)
    )


def _set_phase_status(job: CraftJob, index: int, status: str) -> None:
    phases = list(job.phases or [])
    if 0 <= index < len(phases):
        phases[index] = {**phases[index], "status": status}
        job.phases = phases


def append_job_event(
    db_session: Session,
    *,
    job_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    try:
        db_session.add(
            CraftJobEvent(job_id=job_id, event_type=event_type, payload=payload)
        )
    except AttributeError:
        return


def add_job_checkpoint(
    db_session: Session,
    *,
    job_id: UUID,
    ns: str,
    step: int,
    writes: dict[str, Any],
) -> None:
    try:
        db_session.add(
            CraftJobCheckpoint(job_id=job_id, ns=ns, step=step, writes=writes)
        )
    except AttributeError:
        return


def list_job_checkpoints(
    db_session: Session, *, job_id: UUID, ns: str | None = None
) -> list[CraftJobCheckpoint]:
    stmt = select(CraftJobCheckpoint).where(CraftJobCheckpoint.job_id == job_id)
    if ns is not None:
        stmt = stmt.where(CraftJobCheckpoint.ns == ns)
    stmt = stmt.order_by(
        CraftJobCheckpoint.step.asc(), CraftJobCheckpoint.created_at.asc()
    )
    return list(db_session.scalars(stmt))


def list_job_events(
    db_session: Session, *, job_id: UUID, limit: int = 50
) -> list[CraftJobEvent]:
    stmt = (
        select(CraftJobEvent)
        .where(CraftJobEvent.job_id == job_id)
        .order_by(CraftJobEvent.created_at.desc())
        .limit(limit)
    )
    return list(reversed(list(db_session.scalars(stmt))))


def mark_job_waiting_lanes(job: CraftJob) -> None:
    job.status = CraftJobStatus.WAITING_LANES


def mark_job_interrupted(job: CraftJob) -> None:
    job.status = CraftJobStatus.INTERRUPTED
