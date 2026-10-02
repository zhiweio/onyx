"""Advance a Craft long job after a turn releases the prompt slot."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from onyx.cache.factory import get_cache_backend
from onyx.configs.constants import MessageType
from onyx.db.craft_job import (
    get_open_job_for_session,
    get_specialist_for_session,
    job_is_terminal,
    job_total_budget_exhausted,
    mark_job_finished,
    mark_specialist_finished,
)
from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import CraftJob
from onyx.server.features.build.db.build_session import (
    count_user_messages,
    create_message,
)
from onyx.server.features.build.interactive_turns.executor import (
    start_interactive_turn_runner,
)
from onyx.server.features.build.interactive_turns.state import (
    InteractiveTurnLockError,
    acquire_active_turn_lock,
    create_interactive_turn,
    get_active_turn,
)
from onyx.server.features.build.jobs.gates import retry_brief, retry_limit_error_detail
from onyx.server.features.build.jobs.phase_gate import (
    DEFAULT_PHASE_RETRY_LIMIT,
    increment_gate_retries,
    pop_pending_enqueue_prompt,
    set_pending_enqueue_prompt,
)
from onyx.server.features.build.jobs.plan import (
    PLAN_JSON_PATH,
    apply_plan_to_job_phases,
    parse_plan_bytes,
)
from onyx.server.features.build.jobs.protocol import current_phase
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.utils.logger import setup_logger

logger = setup_logger()


def maybe_continue_craft_job(
    db_session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    sandbox_id: UUID,
    turn_succeeded: bool,
    deadline_exceeded: bool,
    cancelled: bool,
    lease_owner: str | None = None,
    turn_error_detail: str | None = None,
) -> None:
    specialist = get_specialist_for_session(db_session, session_id)
    if specialist is not None:
        _finish_specialist_turn(
            db_session,
            specialist_session_id=session_id,
            user_id=user_id,
            turn_succeeded=turn_succeeded,
            cancelled=cancelled,
            lease_owner=lease_owner,
            turn_error_detail=turn_error_detail,
        )
        return

    job = get_open_job_for_session(db_session, session_id)
    if job is None:
        return
    if cancelled:
        mark_job_finished(job, status=CraftJobStatus.CANCELLED)
        db_session.commit()
        return
    if job.status in {
        CraftJobStatus.WAITING_LANES,
        CraftJobStatus.INTERRUPTED,
    }:
        if job.status == CraftJobStatus.WAITING_LANES:
            from onyx.server.features.build.jobs.kernel import reap_inactive_lanes

            reap_inactive_lanes(db_session, job=job, user_id=user_id)
        return
    if not turn_succeeded and not deadline_exceeded:
        from onyx.server.features.build.jobs.gates import is_transient_turn_error

        phase = current_phase(job.phases, job.current_phase_index)
        if phase is not None and is_transient_turn_error(turn_error_detail):
            # Upstream blips and hard-cap kills leave the workspace intact:
            # retry the phase turn instead of failing the whole job.
            _retry_or_fail_phase(
                db_session,
                job=job,
                user_id=user_id,
                phase=phase,
                missing=[],
                reasons=[turn_error_detail or "phase turn failed"],
            )
            return
        from onyx.server.features.build.jobs.kernel import finalize_job_failure

        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail=_phase_failure_detail(turn_error_detail),
        )
        return
    if job_total_budget_exhausted(job):
        from onyx.server.features.build.jobs.kernel import finalize_job_failure

        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail="Job total budget exhausted",
        )
        return

    from onyx.server.features.build.jobs.kernel import after_worker_turn

    after_worker_turn(
        db_session,
        job=job,
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=session_id,
        deadline_exceeded=deadline_exceeded,
        lease_owner=lease_owner,
    )


def flush_pending_job_enqueue(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
) -> UUID | None:
    """Retry a continuation that missed the turn lock."""
    phase = current_phase(job.phases, job.current_phase_index)
    if phase is None:
        return None
    pending = pop_pending_enqueue_prompt(phase)
    if pending is None:
        return None
    job.phases = _replace_phase(job.phases, job.current_phase_index, phase)
    db_session.commit()
    return _enqueue_or_remember(
        db_session,
        job=job,
        user_id=user_id,
        phase=phase,
        prompt=pending,
    )


def _phase_failure_detail(turn_error_detail: str | None) -> str:
    if turn_error_detail:
        return f"Phase turn failed: {turn_error_detail}"
    return "Phase turn failed"


def _retry_or_fail_phase(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    phase: dict,
    missing: list[str],
    reasons: list[str] | None = None,
) -> None:
    retries = increment_gate_retries(phase)
    job.phases = _replace_phase(job.phases, job.current_phase_index, phase)
    if retries >= DEFAULT_PHASE_RETRY_LIMIT:
        from onyx.server.features.build.jobs.kernel import finalize_job_failure

        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail=retry_limit_error_detail(
                *(missing or [str(phase.get("id") or "")])
            ),
        )
        return
    db_session.commit()
    phase_id = str(phase.get("id") or "")
    prompt = retry_brief(phase_id, missing, reasons=reasons)
    _enqueue_or_remember(
        db_session,
        job=job,
        user_id=user_id,
        phase=phase,
        prompt=prompt,
    )


def _apply_disk_plan(job: CraftJob, *, sandbox_id: UUID, session_id: UUID) -> None:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, PLAN_JSON_PATH)
        plan = parse_plan_bytes(raw)
    except Exception:
        return
    job.phases = apply_plan_to_job_phases(list(job.phases or []), plan)


def _enqueue_or_remember(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    phase: dict,
    prompt: str,
) -> UUID | None:
    turn_id = _enqueue_phase_turn(
        db_session,
        session_id=job.session_id,
        user_id=user_id,
        prompt=prompt,
    )
    if turn_id is None:
        set_pending_enqueue_prompt(phase, prompt)
        job.phases = _replace_phase(job.phases, job.current_phase_index, phase)
        db_session.commit()
    return turn_id


def _replace_phase(phases: list[dict], index: int, phase: dict) -> list[dict]:
    updated = list(phases or [])
    if 0 <= index < len(updated):
        updated[index] = dict(phase)
    return updated


def _finish_specialist_turn(
    db_session: Session,
    *,
    specialist_session_id: UUID,
    user_id: UUID,
    turn_succeeded: bool,
    cancelled: bool,
    lease_owner: str | None = None,
    turn_error_detail: str | None = None,
) -> None:
    specialist = get_specialist_for_session(db_session, specialist_session_id)
    if specialist is None:
        return
    if cancelled:
        mark_specialist_finished(
            specialist,
            status=CraftJobSpecialistStatus.FAILED,
            error_detail="Cancelled",
        )
    elif turn_succeeded:
        mark_specialist_finished(specialist, status=CraftJobSpecialistStatus.SUCCEEDED)
    else:
        mark_specialist_finished(
            specialist,
            status=CraftJobSpecialistStatus.FAILED,
            error_detail=turn_error_detail or "Specialist turn failed",
        )
    db_session.commit()

    job = specialist.job
    if job is None or job_is_terminal(job):
        return
    if job_total_budget_exhausted(job):
        from onyx.server.features.build.jobs.kernel import finalize_job_failure

        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail="Job total budget exhausted",
        )
        return

    from onyx.server.features.build.jobs.kernel import after_lane_turn

    # specialist_ok reflects ONLY this lane's own outcome; whether some other
    # lane failed is a job-level decision made after all lanes are terminal.
    after_lane_turn(
        db_session,
        job=job,
        user_id=user_id,
        specialist_ok=turn_succeeded and not cancelled,
        node_id=specialist.node_id,
        lease_owner=lease_owner,
        turn_error_detail=turn_error_detail,
        specialist_session_id=specialist.session_id,
    )


def enqueue_job_phase_turn(
    db_session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    prompt: str,
    visible_user_text: str | None = None,
    selected_skill_ids: list[str] | None = None,
    selected_mcp_server_ids: list[int] | None = None,
) -> UUID | None:
    return _enqueue_phase_turn(
        db_session,
        session_id=session_id,
        user_id=user_id,
        prompt=prompt,
        visible_user_text=visible_user_text,
        selected_skill_ids=selected_skill_ids,
        selected_mcp_server_ids=selected_mcp_server_ids,
    )


def _job_for_turn_session(db_session: Session, session_id: UUID) -> CraftJob | None:
    try:
        job = get_open_job_for_session(db_session, session_id)
        if job is not None:
            return job
        specialist = get_specialist_for_session(db_session, session_id)
        return specialist.job if specialist is not None else None
    except Exception:
        return None


def _enqueue_phase_turn(
    db_session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    prompt: str,
    visible_user_text: str | None = None,
    selected_skill_ids: list[str] | None = None,
    selected_mcp_server_ids: list[int] | None = None,
) -> UUID | None:
    cache = get_cache_backend()
    try:
        lock = acquire_active_turn_lock(cache, session_id)
    except InteractiveTurnLockError:
        logger.warning("Could not lock session %s to continue a Craft job", session_id)
        return None
    try:
        if get_active_turn(cache=cache, session_id=session_id, user_id=user_id):
            logger.info(
                "Session %s already has a turn; skip job continuation", session_id
            )
            return None
        if selected_skill_ids is None or selected_mcp_server_ids is None:
            from onyx.server.features.build.jobs.mcp import job_picker_selection

            job = _job_for_turn_session(db_session, session_id)
            if job is not None:
                stored_skills, stored_mcp = job_picker_selection(job)
                if selected_skill_ids is None:
                    selected_skill_ids = stored_skills
                if selected_mcp_server_ids is None:
                    selected_mcp_server_ids = stored_mcp
        turn_index = count_user_messages(session_id, db_session)
        visible = visible_user_text.strip() if visible_user_text else ""
        create_message(
            session_id=session_id,
            message_type=MessageType.USER,
            turn_index=turn_index,
            message_metadata={
                "type": "user_message",
                "content": {
                    "type": "text",
                    "text": visible,
                },
                "craft_job_continue": not bool(visible),
            },
            db_session=db_session,
        )
        turn = create_interactive_turn(
            cache=cache,
            session_id=session_id,
            user_id=user_id,
            client_request_id=str(uuid4()),
            prompt=prompt,
            turn_index=turn_index,
            selected_skill_ids=selected_skill_ids or [],
            selected_mcp_server_ids=selected_mcp_server_ids or [],
        )
        db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception("Failed to enqueue Craft job continuation")
        return None
    finally:
        lock.release()

    start_interactive_turn_runner(turn.turn_id)
    return turn.turn_id


def job_turn_budgets(job: CraftJob | None) -> tuple[int, int] | None:
    """Return (soft_budget, hard_cap) for a job turn, or None for defaults.

    Deep-job turns (plan phases and lane specialists) routinely exceed the
    interactive 30-minute promise, so the cap floors at the interactive cap
    and ceilings at the scheduled-run cap regardless of the configured phase
    budget.
    """
    if job is None:
        return None
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_SOFT_BUDGET_FRACTION
    from onyx.server.features.build.timeouts import (
        INTERACTIVE_TURN_HARD_CAP_SECONDS,
        SCHEDULED_RUN_HARD_CAP_SECONDS,
    )

    hard = min(
        max(job.phase_budget_seconds, INTERACTIVE_TURN_HARD_CAP_SECONDS),
        SCHEDULED_RUN_HARD_CAP_SECONDS,
    )
    soft = max(1, int(CRAFT_DEEP_JOB_SOFT_BUDGET_FRACTION * hard))
    return soft, hard
