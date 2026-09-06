"""Database operations for Craft long jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import CraftJob, CraftJobSpecialist

OPEN_JOB_STATUSES = (
    CraftJobStatus.PENDING,
    CraftJobStatus.RUNNING,
    CraftJobStatus.WAITING_SPECIALISTS,
)


def get_craft_job(db_session: Session, job_id: UUID) -> CraftJob | None:
    return db_session.scalar(
        select(CraftJob)
        .options(selectinload(CraftJob.specialists))
        .where(CraftJob.id == job_id)
    )


def get_craft_job_for_user(
    db_session: Session, job_id: UUID, user_id: UUID
) -> CraftJob | None:
    job = get_craft_job(db_session, job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


def get_open_job_for_session(
    db_session: Session, session_id: UUID
) -> CraftJob | None:
    return db_session.scalar(
        select(CraftJob)
        .options(selectinload(CraftJob.specialists))
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
        .options(selectinload(CraftJob.specialists))
        .where(CraftJob.session_id == session_id)
        .order_by(CraftJob.created_at.desc())
        .limit(1)
    )


def get_specialist_for_session(
    db_session: Session, session_id: UUID
) -> CraftJobSpecialist | None:
    return db_session.scalar(
        select(CraftJobSpecialist)
        .options(selectinload(CraftJobSpecialist.job))
        .where(CraftJobSpecialist.session_id == session_id)
    )


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


def job_total_budget_exhausted(job: CraftJob) -> bool:
    if job.started_at is None:
        return False
    started = job.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return elapsed >= job.total_budget_seconds


def add_specialist(
    db_session: Session,
    *,
    job: CraftJob,
    session_id: UUID,
    role: str,
    prompt: str,
) -> CraftJobSpecialist:
    row = CraftJobSpecialist(
        job_id=job.id,
        session_id=session_id,
        role=role[:64],
        prompt=prompt,
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
) -> None:
    specialist.status = status
    specialist.error_detail = error_detail
    specialist.finished_at = datetime.now(timezone.utc)


def specialists_all_terminal(job: CraftJob) -> bool:
    if not job.specialists:
        return True
    return all(
        row.status
        in (CraftJobSpecialistStatus.SUCCEEDED, CraftJobSpecialistStatus.FAILED)
        for row in job.specialists
    )


def specialists_any_failed(job: CraftJob) -> bool:
    return any(
        row.status == CraftJobSpecialistStatus.FAILED for row in job.specialists
    )


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
