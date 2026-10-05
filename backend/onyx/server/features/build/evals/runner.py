"""Headless runner for one craft eval case.

Mirrors the scheduled-task executor's drive loop (``ensure_sandbox_running``
→ dedicated ``origin=EVAL`` session → ``yield_sandbox_events`` with a
wall-clock budget) but stays separate from it on purpose: the eval state
machine lives in ``craft_eval_run``/``craft_eval_case_result``, there is no
approval gate, and after the turn the runner collects deliverables and hands
them to the judge. Keeping this importable-and-testable without a Celery
worker follows the same split as ``run_scheduled_task_logic``.

Never raises: every failure path writes a terminal case result (ERROR) so
the pipeline can move on to the next case.
"""

from __future__ import annotations

import time
from uuid import UUID

from fastapi_users.password import PasswordHelper
from sqlalchemy.orm import Session

from onyx.configs.constants import MessageType
from onyx.db.craft_evals import mark_case_result
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import AccountType, CraftEvalCaseStatus, SessionOrigin
from onyx.db.models import Sandbox, User
from onyx.db.users import (
    assign_user_to_default_groups__no_commit,
    get_user_by_email,
    is_limited_user,
)
from onyx.server.features.build.configs import (
    CRAFT_EVAL_CASE_BUDGET_SECONDS,
    CRAFT_EVAL_USER_EMAIL,
)
from onyx.server.features.build.db.build_session import create_message
from onyx.server.features.build.db.sandbox import update_sandbox_heartbeat
from onyx.server.features.build.evals.judge import judge_case
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.server.features.build.sandbox.event_schema import (
    TURN_ERROR_CODE_TIMEOUT,
    Error,
    PromptResponse,
)
from onyx.server.features.build.sandbox.tape_recorder import (
    flush_tape,
    tape_recording,
)
from onyx.server.features.build.session.locks import session_creation_lock
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.build.session.streaming import BuildStreamingState
from onyx.server.features.build.timeouts import PROVISION_WAIT_SECONDS
from onyx.server.metrics.craft_evals import record_case_outcome
from onyx.system_catalog.builtin.evals.loader import EvalCase
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Deliverable read budget: a judge prompt only ever sees text under this
# size; charts and other binaries are skipped by the caller.
_ARTIFACT_MAX_BYTES = 512 * 1024


def ensure_eval_user(db_session: Session) -> User:
    """The dedicated service account owning eval sessions/sandboxes.

    Created on first use and added to the default Basic group: a
    SERVICE_ACCOUNT with no group membership counts as "limited" and is
    denied by ``current_user`` (the LLM gateway rejects its PAT), so the
    group assignment is load-bearing, not cosmetic. It never logs in
    (random password hash).
    """
    user = get_user_by_email(CRAFT_EVAL_USER_EMAIL, db_session)
    if user is not None:
        _ensure_eval_user_not_limited(db_session, user)
        return user
    user = User(
        email=CRAFT_EVAL_USER_EMAIL,
        hashed_password=PasswordHelper().hash(PasswordHelper().generate()),
        is_active=True,
        is_verified=True,
        account_type=AccountType.SERVICE_ACCOUNT,
    )
    db_session.add(user)
    try:
        assign_user_to_default_groups__no_commit(db_session, user)
        db_session.commit()
        return user
    except Exception:
        db_session.rollback()
        concurrent = get_user_by_email(CRAFT_EVAL_USER_EMAIL, db_session)
        if concurrent is None:
            raise
        return concurrent


def _ensure_eval_user_not_limited(db_session: Session, user: User) -> None:
    """Repair a pre-existing eval user that predates the group assignment
    (e.g. created by an earlier run). Idempotent and best-effort."""
    if not is_limited_user(user):
        return
    try:
        assign_user_to_default_groups__no_commit(db_session, user)
        db_session.commit()
        logger.info("Repaired eval service account group membership")
    except Exception:
        db_session.rollback()
        logger.exception("Failed to repair eval service account permissions")


def run_eval_case(run_id: UUID, result_id: int, case: EvalCase) -> None:
    """Execute one case end-to-end and write its terminal case result."""
    budget_seconds = case.budget_seconds or CRAFT_EVAL_CASE_BUDGET_SECONDS
    started = time.monotonic()

    # ---- Phase A: eval user, sandbox, session, fixtures --------------------
    try:
        sandbox_id, session_id, eval_user_id = _setup_case(result_id, case)
    except Exception as exc:
        logger.exception("Eval case %s failed in setup", case.slug)
        _mark_error(run_id, result_id, case.slug, f"setup failed: {exc}")
        record_case_outcome("error")
        return

    # ---- Phase B: drive the agent ------------------------------------------
    drive_error = _drive_case(
        case,
        sandbox_id=sandbox_id,
        session_id=session_id,
        eval_user_id=eval_user_id,
        budget_seconds=budget_seconds,
    )
    if drive_error is not None:
        _mark_error(
            run_id,
            result_id,
            case.slug,
            drive_error,
            duration_seconds=time.monotonic() - started,
        )
        record_case_outcome("error")
        return

    # ---- Phase C: collect deliverables + judge ------------------------------
    try:
        artifacts = _collect_artifacts(sandbox_id, session_id, case)
        judgement = judge_case(case, artifacts)
        with get_session_with_current_tenant() as db_session:
            mark_case_result(
                db_session,
                result_id,
                status=judgement.status,
                score=judgement.score,
                deterministic_findings=judgement.deterministic,
                judge_verdict=judgement.judge,
                duration_seconds=time.monotonic() - started,
            )
            db_session.commit()
        record_case_outcome(judgement.status.value)
        logger.info(
            "Eval case %s done: status=%s score=%s",
            case.slug,
            judgement.status.value,
            judgement.score,
        )
    except Exception as exc:
        logger.exception("Eval case %s failed in judging", case.slug)
        _mark_error(
            run_id,
            result_id,
            case.slug,
            f"judge failed: {exc}",
            duration_seconds=time.monotonic() - started,
        )
        record_case_outcome("error")


def _setup_case(result_id: int, case: EvalCase) -> tuple[UUID, UUID, UUID]:
    """Create the eval user's sandbox + EVAL session and seed fixtures.

    Returns (sandbox_id, session_id, eval_user_id).
    """
    with get_session_with_current_tenant() as db_session:
        mark_case_result(
            db_session, result_id, status=CraftEvalCaseStatus.RUNNING
        )
        db_session.commit()

        eval_user = ensure_eval_user(db_session)
        session_manager = SessionManager(db_session)
        sandbox = session_manager.ensure_sandbox_running(
            eval_user.id,
            provisioning_wait_seconds=PROVISION_WAIT_SECONDS,
        )
        db_session.commit()

        with session_creation_lock(eval_user.id):
            build_session = session_manager.create_session(
                user_id=eval_user.id,
                origin=SessionOrigin.EVAL,
                name=f"Eval: {case.name}",
            )
            session_id = build_session.id

            create_message(
                session_id=session_id,
                message_type=MessageType.USER,
                turn_index=0,
                message_metadata={
                    "type": "user_message",
                    "content": {"type": "text", "text": case.user_prompt},
                },
                db_session=db_session,
            )
            mark_case_result(db_session, result_id, session_id=session_id)

            # Bind the case's vertical skills into the session subset
            # before the first turn (platform-side seeding, not
            # request_skill: the eval measures task quality, not the
            # self-extension path).
            session_manager.extend_session_skills(
                sandbox, build_session, list(case.skill_slugs)
            )
            update_sandbox_heartbeat(db_session, sandbox.id)
            db_session.commit()

        sandbox_id = sandbox.id
        eval_user_id = eval_user.id

    for item in case.inputs:
        get_sandbox_manager().write_sandbox_file(
            sandbox_id,
            f"sessions/{session_id}/{item.path}",
            item.read(),
        )
    return sandbox_id, session_id, eval_user_id


def _drive_case(
    case: EvalCase,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    eval_user_id: UUID,
    budget_seconds: int,
) -> str | None:
    """Run the single agent turn. Returns an error string, or None on a
    clean completion."""
    with get_session_with_current_tenant() as db_session:
        session_manager = SessionManager(db_session)
        try:
            eval_user = db_session.get(User, eval_user_id)
            build_session = session_manager.get_session(session_id, eval_user_id)
            sandbox_row = db_session.get(Sandbox, sandbox_id)
            if eval_user is None or build_session is None or sandbox_row is None:
                return "eval session context lost before turn"
            # Hermetic by design: the eval user binds zero MCP servers.
            session_manager.reconcile_session_llm_config(
                sandbox_row, build_session, eval_user, allowed_server_ids=()
            )
            session_manager.stamp_turn_deadline(
                sandbox_id,
                session_id,
                soft_budget_seconds=budget_seconds,
                hard_cap_seconds=budget_seconds,
            )
            db_session.commit()

            state = BuildStreamingState(turn_index=0)
            deadline = time.monotonic() + budget_seconds
            prompt_slot_cm = session_manager.prompt_slot(sandbox_id, session_id)
            slot = prompt_slot_cm.__enter__()
            if not slot.acquired:
                prompt_slot_cm.__exit__(None, None, None)
                return "concurrent turn in eval session"
            try:
                with tape_recording(session_id, 0, "eval"):
                    terminal_error: Error | None = None
                    got_response = False
                    cancelled = False
                    for sandbox_event in session_manager.yield_sandbox_events(
                        sandbox_id,
                        session_id,
                        case.user_prompt,
                        turn_timeout_seconds=float(budget_seconds),
                    ):
                        slot.extend()
                        if slot.lost:
                            return "prompt slot lease lost mid-turn"
                        if isinstance(sandbox_event, Error):
                            terminal_error = sandbox_event
                            break
                        if isinstance(sandbox_event, PromptResponse):
                            if (
                                getattr(  # ods: ignore[getattr]
                                    sandbox_event, "stop_reason", None
                                )
                                == "cancelled"
                            ):
                                cancelled = True
                            got_response = True
                            break
                        if time.monotonic() > deadline:
                            return f"budget exceeded ({budget_seconds}s)"
                        session_manager.persist_sandbox_event(
                            session_id, state, sandbox_event
                        )
                        db_session.commit()
                    flush_tape(db_session)

                if terminal_error is not None:
                    if terminal_error.code == TURN_ERROR_CODE_TIMEOUT:
                        return f"turn timeout: {terminal_error.message}"
                    return terminal_error.message or "agent turn error"
                if cancelled:
                    return "agent turn was aborted before completion"
                if not got_response:
                    return "agent stream ended without a completion response"

                session_manager.finalize_persist(session_id, state)
                db_session.commit()
                return None
            finally:
                if not slot.lost:
                    session_manager.clear_turn_deadline(sandbox_id, session_id)
                prompt_slot_cm.__exit__(None, None, None)
        except Exception as exc:
            logger.exception("Eval session %s failed while driving", session_id)
            db_session.rollback()
            return f"{type(exc).__name__}: {exc}"


def _collect_artifacts(
    sandbox_id: UUID, session_id: UUID, case: EvalCase
) -> dict[str, str]:
    manager = get_sandbox_manager()
    artifacts: dict[str, str] = {}
    for path in case.expected_paths:
        try:
            raw = manager.read_file(sandbox_id, session_id, path)
        except Exception:
            continue  # missing deliverable — recorded by the judge
        if len(raw) > _ARTIFACT_MAX_BYTES:
            raw = raw[:_ARTIFACT_MAX_BYTES]
        artifacts[path] = raw.decode("utf-8", errors="replace")
    return artifacts


def _mark_error(
    run_id: UUID,
    result_id: int,
    case_slug: str,
    detail: str,
    *,
    duration_seconds: float | None = None,
) -> None:
    try:
        with get_session_with_current_tenant() as db_session:
            mark_case_result(
                db_session,
                result_id,
                status=CraftEvalCaseStatus.ERROR,
                error_detail=detail,
                duration_seconds=duration_seconds,
            )
            db_session.commit()
    except Exception:
        logger.exception(
            "Failed to record ERROR for eval case %s (run %s)", case_slug, run_id
        )
