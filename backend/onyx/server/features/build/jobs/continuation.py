"""Advance a Craft long job after a turn releases the prompt slot."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from onyx.cache.factory import get_cache_backend
from onyx.configs.constants import MessageType
from onyx.db.craft_job import (
    advance_job_phase,
    get_open_job_for_session,
    get_specialist_for_session,
    job_total_budget_exhausted,
    mark_job_finished,
    mark_job_running,
    mark_specialist_finished,
    specialists_all_terminal,
    specialists_any_failed,
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
from onyx.server.features.build.jobs.protocol import (
    PHASE_DONE_PATH,
    compose_phase_index,
    continuation_prompt,
    current_phase,
    phase_index_by_id,
)
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
) -> None:
    specialist = get_specialist_for_session(db_session, session_id)
    if specialist is not None:
        _finish_specialist_turn(
            db_session,
            specialist_session_id=session_id,
            user_id=user_id,
            turn_succeeded=turn_succeeded,
            cancelled=cancelled,
        )
        return

    job = get_open_job_for_session(db_session, session_id)
    if job is None:
        return
    if cancelled:
        mark_job_finished(job, status=CraftJobStatus.CANCELLED)
        db_session.commit()
        return
    if job.status == CraftJobStatus.WAITING_SPECIALISTS:
        return
    if not turn_succeeded and not deadline_exceeded:
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="Phase turn failed",
        )
        db_session.commit()
        return
    if job_total_budget_exhausted(job):
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="Job total budget exhausted",
        )
        db_session.commit()
        return

    done_id = _read_phase_done(sandbox_id, session_id)
    phase = current_phase(job.phases, job.current_phase_index)
    if phase is not None and done_id and done_id != phase.get("id"):
        matched = phase_index_by_id(job.phases, done_id)
        if matched is not None:
            job.current_phase_index = matched

    next_index = job.current_phase_index + 1
    if next_index >= len(job.phases):
        mark_job_finished(job, status=CraftJobStatus.SUCCEEDED)
        db_session.commit()
        return

    advance_job_phase(job, next_index)
    db_session.commit()
    next_phase = current_phase(job.phases, next_index)
    if next_phase is None:
        return
    prompt = continuation_prompt(phase=next_phase, domain=job.domain, job_name=job.name)
    _enqueue_phase_turn(
        db_session,
        session_id=job.session_id,
        user_id=user_id,
        prompt=prompt,
    )


def _finish_specialist_turn(
    db_session: Session,
    *,
    specialist_session_id: UUID,
    user_id: UUID,
    turn_succeeded: bool,
    cancelled: bool,
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
            error_detail="Specialist turn failed",
        )
    db_session.commit()

    job = specialist.job
    if job is None or not specialists_all_terminal(job):
        return
    if specialists_any_failed(job):
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="A specialist session failed",
        )
        db_session.commit()
        return
    if job_total_budget_exhausted(job):
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="Job total budget exhausted",
        )
        db_session.commit()
        return

    compose_index = compose_phase_index(job.phases)
    advance_job_phase(job, compose_index)
    mark_job_running(job)
    db_session.commit()
    phase = current_phase(job.phases, compose_index)
    if phase is None:
        return
    prompt = continuation_prompt(phase=phase, domain=job.domain, job_name=job.name)
    prompt += (
        "\nSpecialists finished. Read `project/research/` and "
        "`project/extracted/` before you write the report."
    )
    _enqueue_phase_turn(
        db_session,
        session_id=job.session_id,
        user_id=user_id,
        prompt=prompt,
    )


def enqueue_job_phase_turn(
    db_session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    prompt: str,
) -> UUID | None:
    return _enqueue_phase_turn(
        db_session, session_id=session_id, user_id=user_id, prompt=prompt
    )


def _enqueue_phase_turn(
    db_session: Session,
    *,
    session_id: UUID,
    user_id: UUID,
    prompt: str,
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
        turn_index = count_user_messages(session_id, db_session)
        create_message(
            session_id=session_id,
            message_type=MessageType.USER,
            turn_index=turn_index,
            message_metadata={
                "type": "user_message",
                "content": {"type": "text", "text": prompt},
                "craft_job_continue": True,
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


def _read_phase_done(sandbox_id: UUID, session_id: UUID) -> str | None:
    try:
        raw = get_sandbox_manager().read_file(sandbox_id, session_id, PHASE_DONE_PATH)
    except Exception:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    return text.splitlines()[0].strip()


def job_turn_budgets(job: CraftJob | None) -> tuple[int, int] | None:
    """Return (soft_budget, hard_cap) for a job turn, or None for defaults."""
    if job is None:
        return None
    from onyx.server.features.build.configs import (
        CRAFT_DEEP_JOB_RESOURCES,
        CRAFT_DEEP_JOB_SOFT_BUDGET_FRACTION,
    )
    from onyx.server.features.build.timeouts import (
        INTERACTIVE_TURN_HARD_CAP_SECONDS,
        TURN_SOFT_BUDGET_FRACTION,
    )

    hard = min(job.phase_budget_seconds, INTERACTIVE_TURN_HARD_CAP_SECONDS)
    fraction = (
        CRAFT_DEEP_JOB_SOFT_BUDGET_FRACTION
        if CRAFT_DEEP_JOB_RESOURCES
        else TURN_SOFT_BUDGET_FRACTION
    )
    soft = max(1, int(fraction * hard))
    return soft, hard
