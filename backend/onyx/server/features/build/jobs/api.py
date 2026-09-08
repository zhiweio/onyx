from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.cache.factory import get_cache_backend
from onyx.db.craft_job import (
    create_craft_job,
    get_craft_job_for_user,
    get_latest_job_for_session,
    get_open_job_for_session,
    mark_job_finished,
    mark_job_running,
)
from onyx.db.craft_project import require_project_for_user
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import CraftJobStatus, Permission, SandboxStatus
from onyx.db.models import User
from onyx.db.scenario import get_scenario_for_user
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.configs import (
    CRAFT_DEEP_JOB_PHASE_BUDGET_SECONDS,
    CRAFT_DEEP_JOB_TOTAL_BUDGET_SECONDS,
)
from onyx.server.features.build import question_ask
from onyx.server.features.build.db.build_session import get_build_session
from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.server.features.build.jobs.continuation import (
    enqueue_job_phase_turn,
    flush_pending_job_enqueue,
)
from onyx.server.features.build.jobs.kernel import (
    apply_deep_job_sandbox_resources,
    initialize_job_state,
    resume_job,
    start_run_journal,
)
from onyx.server.features.build.jobs.models import (
    CraftJobCreateRequest,
    CraftJobResponse,
    CraftJobResumeRequest,
    QuestionAskDecisionRequest,
    CraftJobStartResponse,
)
from onyx.server.features.build.jobs.protocol import default_phases_for_domain
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.query_and_chat.token_limit import check_token_rate_limits
from shared_configs.contextvars import get_current_tenant_id

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
    scenario_rules: dict[str, object] | None = None
    if scenario_id is not None:
        scenario = get_scenario_for_user(db_session, scenario_id, user)
        scenario_rules = scenario.rules or {}
        if not domain:
            raw_domain = scenario_rules.get("domain")
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
    if request.provider_id is not None and request.model:
        from onyx.server.features.build.session.llm_config import GatewaySelection

        session.agent_provider, session.agent_model = GatewaySelection(
            request.provider_id, request.model
        ).to_columns()
    elif request.provider and request.model:
        session.agent_provider = request.provider
        session.agent_model = request.model

    goal = (request.prompt or name).strip()
    initialize_job_state(job, goal=goal)
    mark_job_running(job)
    start_run_journal(db_session, job)
    apply_deep_job_sandbox_resources(db_session, user_id=user.id)
    db_session.commit()

    turn_id = None
    if request.start:
        from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id
        from onyx.server.features.build.jobs.assembler import assemble_brief
        from onyx.server.features.build.jobs.durability import load_durability_snapshot
        from onyx.server.features.build.jobs.graph import compile_graph
        from onyx.server.features.build.jobs.kernel import load_state

        graph = compile_graph(domain)
        plan_node = graph.get("plan")
        state = load_state(job)
        sandbox = get_sandbox_by_user_id(db_session, user.id)
        from onyx.memory.long_term import recall_texts_for_craft_job

        prompt = (
            assemble_brief(
                node=plan_node,
                state=state,
                job_name=job.name,
                domain=domain,
                user_prompt=goal,
                snapshot=load_durability_snapshot(
                    sandbox_id=sandbox.id if sandbox is not None else None,
                    session_id=session.id,
                ),
                visible_tools=_start_visible_tools(db_session, user),
                recalled_memories=recall_texts_for_craft_job(
                    db_session,
                    user.id,
                    goal,
                    project_id=job.project_id,
                ),
            )
            if plan_node is not None
            else goal
        )
        turn_id = enqueue_job_phase_turn(
            db_session,
            session_id=session.id,
            user_id=user.id,
            prompt=prompt,
            visible_user_text=goal,
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
        CraftJobStatus.WAITING_LANES,
    }:
        flush_pending_job_enqueue(db_session, job=job, user_id=user.id)
        refreshed = get_latest_job_for_session(db_session, session_id)
        if refreshed is not None:
            job = refreshed
    return CraftJobResponse.from_model(job)


@router.get("/asks/current")
def get_current_question_ask(
    session_id: UUID = Query(),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> question_ask.QuestionAskRequest | None:
    if get_build_session(session_id, user.id, db_session) is None:
        raise OnyxError(OnyxErrorCode.SESSION_NOT_FOUND, "Session not found")
    cache = get_cache_backend(tenant_id=get_current_tenant_id())
    current = question_ask.load_current(str(session_id), cache)
    if current is not None:
        question_ask.mark_seen(str(session_id), cache)
    return current


@router.post("/asks/{request_id}/decision")
def resolve_question_ask(
    request_id: str,
    body: QuestionAskDecisionRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> None:
    cache = get_cache_backend(tenant_id=get_current_tenant_id())
    pending = question_ask.load_pending(request_id, cache)
    if pending is None:
        return
    if get_build_session(UUID(pending.build_session_id), user.id, db_session) is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Question request not found.")
    sandbox = get_sandbox_by_user_id(db_session, user.id)
    if sandbox is None or sandbox.status != SandboxStatus.RUNNING:
        raise OnyxError(OnyxErrorCode.SERVICE_UNAVAILABLE, "Sandbox is not running.")
    answers = question_ask.normalize_answers(body.answers, body.answer)
    if pending.kind == "question":
        answered = get_sandbox_manager().answer_question_ask(
            sandbox.id,
            opencode_session_id=pending.opencode_session_id,
            request_id=pending.perm_id,
            directory=pending.directory,
            allow=body.allow,
            answers=answers,
        )
    else:
        answered = get_sandbox_manager().answer_connect_app_permission(
            sandbox.id,
            opencode_session_id=pending.opencode_session_id,
            perm_id=pending.perm_id,
            directory=pending.directory,
            allow=body.allow,
        )
    if not answered:
        raise OnyxError(
            OnyxErrorCode.BAD_GATEWAY,
            "Could not reach the sandbox to apply your choice — please try again.",
        )
    question_ask.clear_pending(request_id, cache)
    question_ask.clear_current(pending.build_session_id, cache)


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
        CraftJobStatus.WAITING_LANES,
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


@router.post("/{job_id}/resume")
def resume_interrupted_job(
    job_id: UUID,
    request: CraftJobResumeRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftJobResponse:
    job = get_craft_job_for_user(db_session, job_id, user.id)
    if job is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    if job.status != CraftJobStatus.INTERRUPTED:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Job is not waiting for approval")
    if request.action not in {"approve", "revise"}:
        mark_job_finished(
            job, status=CraftJobStatus.CANCELLED, error_detail=request.note
        )
        db_session.commit()
        return CraftJobResponse.from_model(job)
    from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id

    sandbox = get_sandbox_by_user_id(db_session, user.id)
    if sandbox is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Sandbox not found")
    resume_job(
        db_session,
        job=job,
        user_id=user.id,
        sandbox_id=sandbox.id,
        action=request.action,
        note=request.note,
    )
    refreshed = get_craft_job_for_user(db_session, job_id, user.id)
    if refreshed is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    return CraftJobResponse.from_model(refreshed)


@router.post("/{job_id}/specialists")
def spawn_specialists(
    job_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftJobResponse:
    if get_craft_job_for_user(db_session, job_id, user.id) is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Job not found")
    raise OnyxError(
        OnyxErrorCode.NOT_IMPLEMENTED,
        "Research lanes start from the job graph. This endpoint is retired.",
    )


def _start_visible_tools(db_session: Session, user: User) -> list[str]:
    try:
        from onyx.server.features.build.sandbox.util.mcp_config import (
            craft_mcp_tool_surface,
        )

        return craft_mcp_tool_surface(db_session, user)
    except Exception:
        return []
