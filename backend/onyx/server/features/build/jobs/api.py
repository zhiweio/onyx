from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.craft_job import (
    add_specialist,
    count_open_specialists,
    create_craft_job,
    get_craft_job_for_user,
    get_latest_job_for_session,
    get_open_job_for_session,
    mark_job_finished,
    mark_job_running,
    mark_job_waiting_specialists,
)
from onyx.db.craft_project import create_project, require_project_for_user
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import CraftJobStatus, Permission, SessionOrigin
from onyx.db.models import User
from onyx.db.scenario import get_scenario_for_user
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.configs import (
    CRAFT_DEEP_JOB_MAX_SPECIALISTS,
    CRAFT_DEEP_JOB_PHASE_BUDGET_SECONDS,
    CRAFT_DEEP_JOB_TOTAL_BUDGET_SECONDS,
)
from onyx.server.features.build.db.build_session import get_build_session
from onyx.server.features.build.jobs.continuation import (
    enqueue_job_phase_turn,
    flush_pending_job_enqueue,
)
from onyx.server.features.build.jobs.models import (
    CraftJobCreateRequest,
    CraftJobResponse,
    CraftJobStartResponse,
    SpecialistsCreateRequest,
)
from onyx.server.features.build.jobs.protocol import (
    default_phases_for_domain,
    first_phase_prompt,
    specialist_prompt,
)
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.query_and_chat.token_limit import check_token_rate_limits

router = APIRouter(prefix="/jobs")


@router.post("")
def create_job(
    request: CraftJobCreateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
    _token_rate_limit_check: None = Depends(check_token_rate_limits),
) -> CraftJobStartResponse:
    session = get_build_session(request.session_id, user.id, db_session)
    if session is None:
        raise OnyxError(OnyxErrorCode.SESSION_NOT_FOUND, "Session not found")
    if get_open_job_for_session(db_session, request.session_id) is not None:
        raise OnyxError(
            OnyxErrorCode.CONFLICT,
            "This session already has a running long job.",
        )

    project_id = request.project_id or session.project_id
    if project_id is not None:
        require_project_for_user(db_session, project_id, user)

    domain = (request.domain or "").strip().lower()
    scenario_id = request.scenario_id or session.scenario_id
    if scenario_id is not None:
        scenario = get_scenario_for_user(db_session, scenario_id, user)
        rules = scenario.rules or {}
        if not domain:
            raw_domain = rules.get("domain")
            if isinstance(raw_domain, str) and raw_domain.strip():
                domain = raw_domain.strip().lower()
    if not domain:
        domain = "general"

    name = (request.name or "").strip() or (request.prompt or "Long job")[:80]
    job = create_craft_job(
        db_session,
        user_id=user.id,
        session_id=session.id,
        name=name,
        domain=domain,
        total_budget_seconds=(
            request.total_budget_seconds or CRAFT_DEEP_JOB_TOTAL_BUDGET_SECONDS
        ),
        phase_budget_seconds=(
            request.phase_budget_seconds or CRAFT_DEEP_JOB_PHASE_BUDGET_SECONDS
        ),
        project_id=project_id,
        scenario_id=scenario_id,
        phases=default_phases_for_domain(domain),
    )
    mark_job_running(job)
    db_session.commit()

    turn_id = None
    if request.start:
        prompt = first_phase_prompt(
            user_prompt=request.prompt or name,
            domain=domain,
            job_name=job.name,
        )
        turn_id = enqueue_job_phase_turn(
            db_session,
            session_id=session.id,
            user_id=user.id,
            prompt=prompt,
        )
    return CraftJobStartResponse(
        job=CraftJobResponse.from_model(job),
        turn_id=turn_id,
    )


@router.get("")
def get_job_for_session(
    session_id: UUID = Query(),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftJobResponse:
    session = get_build_session(session_id, user.id, db_session)
    if session is None:
        raise OnyxError(OnyxErrorCode.SESSION_NOT_FOUND, "Session not found")
    job = get_latest_job_for_session(db_session, session_id)
    if job is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "No long job for this session")
    if job.status in {
        CraftJobStatus.PENDING,
        CraftJobStatus.RUNNING,
        CraftJobStatus.WAITING_SPECIALISTS,
    }:
        flush_pending_job_enqueue(db_session, job=job, user_id=user.id)
        refreshed = get_latest_job_for_session(db_session, session_id)
        if refreshed is not None:
            job = refreshed
    return CraftJobResponse.from_model(job)


@router.get("/{job_id}")
def get_job(
    job_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftJobResponse:
    job = get_craft_job_for_user(db_session, job_id, user.id)
    if job is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    if job.status in {
        CraftJobStatus.PENDING,
        CraftJobStatus.RUNNING,
        CraftJobStatus.WAITING_SPECIALISTS,
    }:
        flush_pending_job_enqueue(db_session, job=job, user_id=user.id)
        refreshed = get_craft_job_for_user(db_session, job_id, user.id)
        if refreshed is not None:
            job = refreshed
    return CraftJobResponse.from_model(job)


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftJobResponse:
    job = get_craft_job_for_user(db_session, job_id, user.id)
    if job is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    if job.status in {
        CraftJobStatus.SUCCEEDED,
        CraftJobStatus.FAILED,
        CraftJobStatus.CANCELLED,
    }:
        return CraftJobResponse.from_model(job)
    mark_job_finished(job, status=CraftJobStatus.CANCELLED)
    db_session.commit()
    try:
        SessionManager(db_session).interrupt_message(job.session_id, user.id)
    except Exception:
        pass
    return CraftJobResponse.from_model(job)


@router.post("/{job_id}/specialists")
def spawn_specialists(
    job_id: UUID,
    request: SpecialistsCreateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
    _token_rate_limit_check: None = Depends(check_token_rate_limits),
) -> CraftJobResponse:
    job = get_craft_job_for_user(db_session, job_id, user.id)
    if job is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    if job.status not in {CraftJobStatus.RUNNING, CraftJobStatus.WAITING_SPECIALISTS}:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Job is not running")
    if not request.specialists:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Add at least one specialist")

    open_count = count_open_specialists(job)
    if open_count + len(request.specialists) > CRAFT_DEEP_JOB_MAX_SPECIALISTS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"At most {CRAFT_DEEP_JOB_MAX_SPECIALISTS} specialists can run at once",
        )

    project_id = request.project_id or job.project_id
    if project_id is None:
        project = create_project(
            db_session, user=user, name=f"{job.name[:100]} blackboard"
        )
        project_id = project.id
        job.project_id = project_id
    else:
        require_project_for_user(db_session, project_id, user)

    session_manager = SessionManager(db_session)
    parent = get_build_session(job.session_id, user.id, db_session)
    scenario_id = job.scenario_id or (parent.scenario_id if parent else None)

    mark_job_waiting_specialists(job)
    db_session.flush()

    for item in request.specialists:
        role = item.role.strip().lower().replace(" ", "_")
        if not role:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Specialist role is required")
        build_session = session_manager.create_session(
            user.id,
            name=f"{job.name[:40]} / {role}"[:128],
            origin=SessionOrigin.JOB,
            scenario_id=scenario_id,
            project_id=project_id,
            headless=True,
        )
        prompt = specialist_prompt(
            role=role, user_prompt=item.prompt, job_name=job.name
        )
        add_specialist(
            db_session,
            job=job,
            session_id=build_session.id,
            role=role,
            prompt=prompt,
        )
        enqueue_job_phase_turn(
            db_session,
            session_id=build_session.id,
            user_id=user.id,
            prompt=prompt,
        )

    db_session.commit()
    refreshed = get_craft_job_for_user(db_session, job.id, user.id)
    if refreshed is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    return CraftJobResponse.from_model(refreshed)
