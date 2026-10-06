"""Background executor for interactive Craft turns."""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.cache.factory import get_cache_backend
from onyx.cache.interface import CACHE_TRANSIENT_ERRORS, CacheBackend
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import BuildSession, CraftJob, Sandbox
from onyx.db.users import fetch_user_by_id
from onyx.server.features.build.configs import (
    CRAFT_JOB_LEASE_TTL_SECONDS,
    OPENCODE_PROMPT_INACTIVITY_TIMEOUT_SECONDS,
)
from onyx.server.features.build.db.build_session import get_build_session
from onyx.server.features.build.db.sandbox import (
    get_sandbox_by_user_id,
    update_sandbox_heartbeat,
)
from onyx.server.features.build.interactive_turns.state import (
    TURN_STATUS_CANCELLED,
    TURN_STATUS_FAILED,
    TURN_STATUS_SUCCEEDED,
    InteractiveTurn,
    InteractiveTurnLockError,
    acquire_active_turn_lock,
    claim_turn_for_runner,
    create_interactive_turn,
    finish_turn,
    get_active_turn,
    get_turn,
    get_turn_for_request,
    touch_turn,
)
from onyx.server.features.build.packets import ContextUsagePacket
from onyx.server.features.build.sandbox.agent_runtime.router import RuntimePurpose
from onyx.server.features.build.sandbox.event_schema import (
    ActivityTimeoutError,
    PromptResponse,
    ToolCallStart,
)
from onyx.server.features.build.sandbox.event_schema import Error as SandboxError
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.server.features.build.sandbox.models import PromptAttachment
from onyx.server.features.build.sandbox.sse import SSEKeepalive
from onyx.server.features.build.session.interrupt_signal import (
    clear_interrupt,
    is_interrupt_requested,
)
from onyx.server.features.build.session.locks import session_creation_lock
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.build.session.sandbox_lifecycle import (
    HEALTH_PROBE_TIMEOUT_SECONDS,
)
from onyx.server.features.build.session.session_ready import (
    ensure_session_ready,
    session_runtime_intact,
)
from onyx.server.features.build.session.streaming import BuildStreamingState
from onyx.server.features.build.timeouts import (
    INTERACTIVE_TURN_HARD_CAP_SECONDS,
    INTERACTIVE_TURN_SOFT_BUDGET_SECONDS,
    PROMPT_SLOT_FAST_FAIL_ACQUIRE_SECONDS,
    PROMPT_SLOT_WAIT_OUT_ORPHAN_SECONDS,
)
from onyx.skills.effective_mcp import resolve_effective_mcp_server_ids
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import (
    CURRENT_TENANT_ID_CONTEXTVAR,
    get_current_tenant_id,
)

logger = setup_logger()

MAX_TIMEOUT_CONTINUATIONS = 2

# A turn must re-prove ownership this many beats in a row before it accepts
# that its job lease is gone and stops streaming.
CRAFT_JOB_LEASE_MAX_MISSED_BEATS = 3
_TOOL_TIMEOUT_CONTINUATION_PROMPT = (
    "Your last step was cancelled — it exceeded the "
    f"{int(OPENCODE_PROMPT_INACTIVITY_TIMEOUT_SECONDS)}s activity limit with no "
    "output. Don't just retry it; split the work into shorter steps or run it in "
    "the background, then continue."
)

_MAX_TOKENS_CONTINUATION_PROMPT = (
    "Your last reply hit the model's output-length limit and was cut off. "
    "Continue exactly where it stopped. Do not repeat text you already wrote. "
    "If the result needs more than one reply, write the full output to a file "
    "under outputs/ and summarize it in the reply."
)


_TURN_ERROR_SUFFIX = (
    "Files written to the workspace are saved — send a follow-up message to continue."
)


class _PromptOutcome(Enum):
    TERMINATED = auto()  # the turn was already finished; the caller returns
    TIMED_OUT = auto()  # step went silent; the caller re-prompts
    COMPLETED = auto()  # the opencode stream ended; run the terminal handling


@dataclass
class _PromptResult:
    outcome: _PromptOutcome
    final_event_seen: bool = False
    cancelled: bool = False
    stop_reason: str | None = None
    used_tokens: int | None = None


def _can_clear_interrupt_fence(
    *,
    cache: CacheBackend,
    turn_id: UUID,
    session_id: UUID,
    user_id: UUID,
    runner_id: str | None,
) -> bool:
    active_turn = get_active_turn(
        cache=cache,
        session_id=session_id,
        user_id=user_id,
    )
    if active_turn is None:
        return True
    return active_turn.turn_id == turn_id and (
        runner_id is None or active_turn.runner_id == runner_id
    )


def start_interactive_turn_runner(turn_id: UUID) -> None:
    """Run an interactive turn in this API process if Redis grants ownership."""
    tenant_id = get_current_tenant_id()

    def run() -> None:
        token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
        turn: InteractiveTurn | None = None
        try:
            turn = claim_turn_for_runner(cache=get_cache_backend(), turn_id=turn_id)
            if turn is None:
                return

            run_claimed_interactive_build_turn(turn)
        except Exception:
            logger.exception("Interactive turn runner failed for turn %s", turn_id)
            if turn is not None:
                finish_turn(
                    cache=get_cache_backend(),
                    turn_id=turn.turn_id,
                    status=TURN_STATUS_FAILED,
                    error_detail="Interactive turn runner failed.",
                    runner_id=turn.runner_id,
                )
        finally:
            CURRENT_TENANT_ID_CONTEXTVAR.reset(token)

    thread = threading.Thread(
        target=run,
        name=f"interactive-build-turn-{turn_id}",
        daemon=True,
    )
    thread.start()


def run_claimed_interactive_build_turn(
    turn: InteractiveTurn,
    *,
    budget_seconds: int = INTERACTIVE_TURN_HARD_CAP_SECONDS,
) -> None:
    """Execute a turn that this runner has already claimed in CacheBackend.

    ``budget_seconds`` is the hard cap; the soft wrap-up steer is sandbox-side
    (turn-budget plugin).
    """
    cache = get_cache_backend()
    runner_id = turn.runner_id
    try:
        _drive_interactive_turn(
            turn_id=turn.turn_id,
            session_id=turn.session_id,
            user_id=turn.user_id,
            prompt=turn.prompt,
            turn_index=turn.turn_index,
            attachments=turn.attachments,
            budget_seconds=budget_seconds,
            runner_id=runner_id,
            reclaimed=turn.reclaimed,
            kind=turn.kind,
            selected_skill_ids=turn.selected_skill_ids,
        )
    except Exception as exc:
        logger.exception(
            "Interactive turn %s failed before drive loop",
            turn.turn_id,
        )
        finish_turn(
            cache=cache,
            turn_id=turn.turn_id,
            status=TURN_STATUS_FAILED,
            error_detail=f"{type(exc).__name__}: {str(exc)[:950]}",
            runner_id=runner_id,
        )


def _ready_session_runtime(
    db_session: Session, session_id: UUID, user_id: UUID
) -> Sandbox:
    """The sandbox this turn runs in, with the session's workspace present.

    A settled session returns straight away; anything else — a sandbox the
    reaper took, a session never restored, a pod that died under a live record —
    is rebuilt through the same path and the same lock the restore endpoint
    uses, blocking, because the turn has nothing to do until the workspace is
    there.

    The pre-lock check is only a fast path: ``ensure_session_ready`` re-verifies
    everything (pod liveness included) under the lock, so it stays with this
    caller — its point is skipping the lock on the hot path, and lock
    acquisition is caller policy (the turn blocks; restore 409s).
    """
    session = get_build_session(session_id, user_id, db_session)
    sandbox = get_sandbox_by_user_id(db_session, user_id)
    if sandbox is not None and session_runtime_intact(session, sandbox):
        # The reaper decides from this timestamp, and the stream only starts
        # refreshing it after the prompt slot and the send.
        update_sandbox_heartbeat(db_session, sandbox.id)
        db_session.commit()
        # RUNNING is a claim, not a fact: the reaper terminates the pod before
        # it writes SLEEPING, and an evicted pod is never written down at all.
        if get_sandbox_manager().health_check(
            sandbox.id, timeout=HEALTH_PROBE_TIMEOUT_SECONDS
        ):
            return sandbox
        logger.warning(
            "Session %s claims a RUNNING sandbox with no live pod; waking it",
            session_id,
        )

    if session is None:
        raise RuntimeError(f"Build session {session_id} not found")
    user = fetch_user_by_id(db_session, user_id)
    if user is None:
        raise RuntimeError(f"User {user_id} not found")

    logger.info(
        "Interactive turn is waking session %s (session=%s sandbox=%s)",
        session_id,
        session.status.value,
        sandbox.status.value if sandbox else "missing",
    )
    with session_creation_lock(user_id):
        return ensure_session_ready(db_session, get_sandbox_manager(), session, user)


def _hold_job_lease(
    job_id: UUID,
    owner: str,
    stop: threading.Event,
    lease_lost: threading.Event,
    tenant_id: str | None,
) -> None:
    """Renew the craft job lease for the duration of one turn.

    The lease starts short and every beat extends it by one more TTL, so a
    beat only has to land once per TTL while the turn streams. After
    ``CRAFT_JOB_LEASE_MAX_MISSED_BEATS`` consecutive failed beats the turn is
    declared lost: it cancels itself instead of writing job state it no longer
    owns, and the lease/fence path takes the job from there.
    """
    token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
    try:
        from onyx.db.craft_job import job_is_terminal
        from onyx.server.features.build.jobs.kernel import renew_lease

        interval = max(CRAFT_JOB_LEASE_TTL_SECONDS / 3, 1)
        missed = 0
        while not stop.wait(interval):
            try:
                with get_session_with_current_tenant() as db_session:
                    job = db_session.get(CraftJob, job_id)
                    if job is None or job_is_terminal(job):
                        return
                    renew_lease(job, owner=owner, seconds=CRAFT_JOB_LEASE_TTL_SECONDS)
                    db_session.commit()
                missed = 0
            except Exception:
                missed += 1
                logger.warning(
                    "Job lease beat %s/%s failed for job %s (owner %s)",
                    missed,
                    CRAFT_JOB_LEASE_MAX_MISSED_BEATS,
                    job_id,
                    owner,
                    exc_info=True,
                )
                if missed >= CRAFT_JOB_LEASE_MAX_MISSED_BEATS:
                    lease_lost.set()
                    return
    finally:
        CURRENT_TENANT_ID_CONTEXTVAR.reset(token)


def _snapshot_session_workspace_after_turn(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    user_id: UUID,
    tenant_id: str | None,
    workspace_touched: bool = True,
) -> threading.Thread:
    """Snapshot the session workspace right after a turn used it.

    Teardown capture (the QM discipline): the snapshot lands while the
    workspace is quiet instead of mid-command. Skipped when the session
    already has a successor turn — including the job continuation this turn
    just enqueued — because the interval sweep snapshots it once idle, and
    the sweep skips fresh snapshots. A turn that ran no tool left the
    workspace untouched, so an existing snapshot still matches and the
    archive is skipped (qm: homeUnchanged). Failures are log-only; the
    sweep remains the fallback.
    """
    from onyx.server.features.build.session.sandbox_lifecycle import (
        create_session_snapshot_keep_latest,
    )

    def _run() -> None:
        token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
        try:
            cache = get_cache_backend()
            if (
                get_active_turn(cache=cache, session_id=session_id, user_id=user_id)
                is not None
            ):
                return
            if not workspace_touched:
                from onyx.server.features.build.db.sandbox import (
                    get_snapshots_for_session,
                )

                with get_session_with_current_tenant() as check_session:
                    if get_snapshots_for_session(check_session, session_id):
                        logger.info(
                            "Teardown snapshot skipped for untouched session %s",
                            session_id,
                        )
                        return
            with get_session_with_current_tenant() as db_session:
                create_session_snapshot_keep_latest(
                    get_sandbox_manager(),
                    db_session,
                    sandbox_id,
                    session_id,
                    str(tenant_id) if tenant_id is not None else "",
                )
            logger.info("Teardown snapshot completed for session %s", session_id)
        except Exception:
            logger.warning(
                "Teardown snapshot failed for session %s", session_id, exc_info=True
            )
        finally:
            CURRENT_TENANT_ID_CONTEXTVAR.reset(token)

    thread = threading.Thread(
        target=_run,
        name=f"craft-teardown-snapshot-{session_id}",
        daemon=True,
    )
    thread.start()
    # Returned so tests can join; callers ignore it.
    return thread


def _context_limit_for(provider: str | None, model: str | None) -> int | None:
    """Context window for the session's model from the runtime registry."""
    if not provider or not model:
        return None
    try:
        from onyx.server.features.build.sandbox.agent_runtime.models import (
            iter_models,
        )

        for spec in iter_models():
            if spec.provider != provider:
                continue
            if model in (
                spec.model_id,
                spec.model_id.rsplit("/", 1)[-1],
                spec.display_name,
            ):
                return spec.context_window
    except Exception:
        logger.warning("Context-limit lookup failed", exc_info=True)
    return None


def _maybe_schedule_auto_compact(
    *,
    cache: CacheBackend,
    session: BuildSession,
    used_tokens: int | None,
    turn_index: int,
) -> None:
    """Compact when the last turn pushed the context past the threshold.

    Manual /compact exists, but users click it only after quality already
    degraded; the usage packet arrives per assistant message, so deciding
    here is free. Only interactive turns: job turns belong to the kernel's
    budget/continuation. Best-effort — a failed schedule leaves the next
    turn to try again."""
    from onyx.server.features.build.configs import CRAFT_AUTO_COMPACT_THRESHOLD

    if CRAFT_AUTO_COMPACT_THRESHOLD <= 0 or used_tokens is None:
        return
    if session.user_id is None or not session.opencode_session_id:
        return
    if not session.agent_provider or not session.agent_model:
        return
    limit = _context_limit_for(session.agent_provider, session.agent_model)
    if limit is None:
        return
    if used_tokens < int(limit * CRAFT_AUTO_COMPACT_THRESHOLD):
        return
    client_request_id = f"auto-compact-{session.id}-{turn_index}"
    lock = None
    try:
        lock = acquire_active_turn_lock(cache, session.id)
        if (
            get_turn_for_request(
                cache=cache,
                session_id=session.id,
                user_id=session.user_id,
                client_request_id=client_request_id,
            )
            is not None
        ):
            return
        if (
            get_active_turn(cache=cache, session_id=session.id, user_id=session.user_id)
            is not None
        ):
            return
        turn = create_interactive_turn(
            cache=cache,
            session_id=session.id,
            user_id=session.user_id,
            client_request_id=client_request_id,
            prompt="",
            turn_index=turn_index,
            kind="compact",
        )
    except InteractiveTurnLockError:
        return
    except Exception:
        logger.warning(
            "Auto-compact turn creation failed for session %s",
            session.id,
            exc_info=True,
        )
        return
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                pass
    logger.info(
        "Auto-compacting session %s: %s tokens of %s window",
        session.id,
        used_tokens,
        limit,
    )
    try:
        start_interactive_turn_runner(turn.turn_id)
    except Exception:
        logger.warning(
            "Auto-compact runner failed to start for session %s",
            session.id,
            exc_info=True,
        )


def _skill_binding_preamble(selected_skill_ids: list[str] | None, prompt: str) -> str:
    """Hidden prefix binding the skills the user explicitly required.

    Applies to turns whose prompt is the raw user text; job briefs state the
    requirement themselves (assembler._required_skill_lines) and are detected
    to avoid doubling it.
    """
    slugs = [slug for slug in (selected_skill_ids or []) if slug]
    if not slugs:
        return ""
    if "user explicitly requires the skill" in prompt.lower():
        return ""
    listed = ", ".join(f"`{slug}`" for slug in slugs)
    return (
        f"[system] The user explicitly requires the skill(s) {listed}. "
        "Load .opencode/skills/<slug>/SKILL.md for each one first, then "
        "follow their workflow for this task. If one of them is missing "
        "from .opencode/skills, say so once and continue with the "
        "scenario pack.\n\n"
    )


def _record_failed_turn(runtime_id: str, outcome: str) -> None:
    from onyx.server.metrics.craft_sandbox import record_turn_outcome

    record_turn_outcome(runtime_id, outcome)


def _drive_interactive_turn(
    *,
    turn_id: UUID,
    session_id: UUID,
    user_id: UUID,
    prompt: str,
    turn_index: int,
    attachments: list[PromptAttachment],
    kind: str = "prompt",
    budget_seconds: int,
    runner_id: str | None,
    reclaimed: bool,
    selected_skill_ids: list[str] | None = None,
) -> None:
    cache = get_cache_backend()
    turn_succeeded = False
    deadline_exceeded = False
    cancelled = False
    # Whether any tool ran this turn. Without a tool call nothing in the
    # session workspace can change, so post-turn cataloging and teardown
    # snapshots can skip the work (qm: homeUnchanged for unused boxes).
    saw_tool_activity = False
    # Error detail of the terminal failure, if any — the job continuation
    # uses it to decide whether the phase/lane turn deserves a retry.
    turn_error_detail: str | None = None
    sandbox_id: UUID | None = None
    skip_job_continue = kind == "compact"
    ownership_lost_for_continue = False
    job_id: UUID | None = None
    lease_stop = threading.Event()
    lease_lost = threading.Event()
    # Tape recording wraps the whole drive: entered once the turn index and
    # session are settled, exited with the turn (the finally below). Kept as
    # an exit stack so early returns before entry have nothing to close.
    from onyx.server.features.build.sandbox.tape_recorder import tape_recording

    tape_stack = contextlib.ExitStack()
    try:
        with get_session_with_current_tenant() as db_session:
            session_manager = SessionManager(db_session)
            sandbox = _ready_session_runtime(db_session, session_id, user_id)
            sandbox_id = sandbox.id
            db_session.commit()
            from onyx.db.craft_job import (
                get_open_job_for_session,
                get_specialist_for_session,
            )
            from onyx.server.features.build.jobs.continuation import job_turn_budgets

            job = get_open_job_for_session(db_session, session_id)
            if job is None:
                specialist = get_specialist_for_session(db_session, session_id)
                job = specialist.job if specialist is not None else None
            budgets = job_turn_budgets(job)
            if budgets is not None:
                _soft_budget_seconds, budget_seconds = budgets
            if job is not None:
                from onyx.server.features.build.jobs.kernel import renew_lease

                job_id = getattr(  # ods: ignore[getattr] — duck-typed job rows
                    job, "id", None
                )
                if job_id is not None:
                    # Short lease held alive by a heartbeat thread: an expired
                    # lease now means the owning turn is really gone, not
                    # long-running.
                    renew_lease(
                        job, owner=str(turn_id), seconds=CRAFT_JOB_LEASE_TTL_SECONDS
                    )
                    db_session.commit()
                    threading.Thread(
                        target=_hold_job_lease,
                        args=(
                            job_id,
                            str(turn_id),
                            lease_stop,
                            lease_lost,
                            get_current_tenant_id(),
                        ),
                        name=f"craft-lease-{turn_id}",
                        daemon=True,
                    ).start()

            if not touch_turn(cache=cache, turn_id=turn_id, runner_id=runner_id):
                logger.info("Interactive turn %s runner ownership lost", turn_id)
                skip_job_continue = True
                return

            state = BuildStreamingState(turn_index=turn_index)
            deadline = time.monotonic() + budget_seconds

            def interrupt_requested() -> bool:
                nonlocal deadline_exceeded
                if time.monotonic() > deadline:
                    deadline_exceeded = True
                    return True
                try:
                    return is_interrupt_requested(session_id, cache)
                except CACHE_TRANSIENT_ERRORS:
                    logger.warning(
                        "[SANDBOX-SERVE] interrupt fence check failed for session %s",
                        session_id,
                        exc_info=True,
                    )
                    return False

            def persist_turn_error(message: str) -> None:
                """Best-effort user-visible failure row; never blocks finish_turn."""
                try:
                    db_session.rollback()
                    session_manager.persist_turn_error(
                        session_id, turn_index, f"{message} {_TURN_ERROR_SUFFIX}"
                    )
                    db_session.commit()
                except Exception:
                    logger.exception(
                        "Failed to persist turn error message for turn %s", turn_id
                    )

            prompt_slot_cm = session_manager.prompt_slot(
                sandbox.id,
                session_id,
                acquire_timeout=(
                    PROMPT_SLOT_WAIT_OUT_ORPHAN_SECONDS
                    if reclaimed
                    else PROMPT_SLOT_FAST_FAIL_ACQUIRE_SECONDS
                ),
            )
            slot = prompt_slot_cm.__enter__()
            if not slot.acquired:
                # Ownership check first: a stalled runner whose turn was reclaimed
                # also lands here, and the successor IS processing the message —
                # it must not leave a false "wasn't processed" row.
                if touch_turn(cache=cache, turn_id=turn_id, runner_id=runner_id):
                    try:
                        session_manager.persist_turn_error(
                            session_id,
                            turn_index,
                            "Another turn was still running for this session, so "
                            "this message wasn't processed. Wait for it to finish, "
                            "then send your message again.",
                        )
                        db_session.commit()
                    except Exception:
                        logger.exception(
                            "Failed to persist turn error message for turn %s", turn_id
                        )
                finish_turn(
                    cache=cache,
                    turn_id=turn_id,
                    status=TURN_STATUS_FAILED,
                    error_detail="Concurrent turn in flight for build session.",
                    runner_id=runner_id,
                )
                prompt_slot_cm.__exit__(None, None, None)
                skip_job_continue = True
                return

            try:
                # Re-check ownership after the (possibly long) slot wait: a reclaim acquire
                # can block past RUNNER_STALE_AFTER_SECONDS, letting another
                # runner steal the turn — it must not reach the prompt POST.
                if not touch_turn(cache=cache, turn_id=turn_id, runner_id=runner_id):
                    logger.info("Interactive turn %s runner ownership lost", turn_id)
                    skip_job_continue = True
                    return

                session = session_manager.get_session(session_id, user_id)
                user = fetch_user_by_id(db_session, user_id)
                if session is None or user is None:
                    raise RuntimeError(
                        "Craft session owner or session no longer exists"
                    )
                turn_state = get_turn(cache, turn_id)
                if job is not None:
                    from onyx.server.features.build.jobs.mcp import (
                        resolve_job_mcp_server_ids,
                    )

                    allowed_mcp_ids = resolve_job_mcp_server_ids(db_session, user, job)
                elif turn_state is not None:
                    skill_ids = turn_state.selected_skill_ids or []
                    if skill_ids:
                        allowed_mcp_ids = resolve_effective_mcp_server_ids(
                            db_session,
                            user,
                            selected_skill_ids=skill_ids,
                        )
                    else:
                        # No per-turn narrowing anywhere: workspace setup injects
                        # every eligible server (minus per-user opt-outs).
                        allowed_mcp_ids = None
                else:
                    allowed_mcp_ids = None
                # The turn may bind skills (chips, scenario, prose) the
                # session's linked catalog does not carry. Extend before
                # reconcile so a regenerated config links the wider subset
                # and the disposed instance re-reads it.
                turn_skill_ids = (
                    list(turn_state.selected_skill_ids or [])
                    if turn_state is not None
                    else []
                )
                if turn_skill_ids:
                    try:
                        session_manager.extend_session_skills(
                            sandbox, session, turn_skill_ids
                        )
                    except Exception:
                        logger.warning(
                            "Skill subset extension failed for session %s",
                            session_id,
                            exc_info=True,
                        )
                session_manager.reconcile_session_llm_config(
                    sandbox, session, user, allowed_server_ids=allowed_mcp_ids
                )
                db_session.commit()

                # Per-turn runtime choice (purpose > request > scenario > org
                # default). Gates the opencode-only flows below.
                runtime_choice = session_manager.resolve_turn_runtime(
                    session,
                    purpose=RuntimePurpose.SCHEDULED
                    if kind != "prompt"
                    else RuntimePurpose.CHAT,
                    requested_runtime=(
                        turn_state.requested_runtime if turn_state is not None else None
                    ),
                )
                runtime_is_opencode = runtime_choice.runtime_id == "opencode"
                # Tape rows must carry the runtime that produced them: the
                # codex replay filters on runtime='codex'. The turn/start
                # fact carries the request environment (provider, model,
                # reasoning effort) so the log alone can reconstruct what
                # the model was asked with.
                tape_stack.enter_context(
                    tape_recording(
                        session_id,
                        turn_index,
                        runtime_choice.runtime_id,
                        turn_id=turn_id,
                        kind=kind,
                        request_env={
                            "provider": session.agent_provider,
                            "model": session.agent_model,
                            "reasoning_effort": (
                                session.reasoning_effort.value
                                if session.reasoning_effort is not None
                                else None
                            ),
                        },
                    )
                )

                # Only while holding the slot — a racing loser must not overwrite
                # the live turn's stamp. Continuations don't restamp.
                # (opencode-only: the budget stamp feeds its turn plugin;
                # codex turns rely on the host hard budget + interrupt.)
                if runtime_is_opencode:
                    session_manager.stamp_turn_deadline(
                        sandbox.id,
                        session_id,
                        soft_budget_seconds=min(
                            (
                                budgets[0]
                                if budgets is not None
                                else INTERACTIVE_TURN_SOFT_BUDGET_SECONDS
                            ),
                            budget_seconds,
                        ),
                        hard_cap_seconds=budget_seconds,
                    )

                if lease_lost.is_set():
                    ownership_lost_for_continue = True
                    finish_turn(
                        cache=cache,
                        turn_id=turn_id,
                        status=TURN_STATUS_FAILED,
                        error_detail="Job lease lost mid-turn.",
                        runner_id=runner_id,
                    )
                    return

                if interrupt_requested():
                    cancelled = not deadline_exceeded
                    session_manager.finalize_persist(session_id, state)
                    db_session.commit()
                    finish_turn(
                        cache=cache,
                        turn_id=turn_id,
                        status=TURN_STATUS_CANCELLED,
                        runner_id=runner_id,
                    )
                    return

                def drive_one_prompt(
                    current_prompt: str,
                    prompt_attachments: list[PromptAttachment],
                    *,
                    can_continue: bool,
                    compact: bool = False,
                ) -> _PromptResult:
                    """Stream one opencode prompt to completion, timeout, or a
                    turn-ending failure. On the recoverable inactivity timeout it
                    returns TIMED_OUT (only while ``can_continue``); failures finish
                    the turn here and return TERMINATED so the caller just returns."""
                    nonlocal deadline_exceeded, ownership_lost_for_continue
                    nonlocal turn_error_detail, saw_tool_activity
                    ownership_lost = False
                    final_event_seen = False
                    cancelled_event_seen = False
                    timed_out = False
                    stop_reason_seen: str | None = None
                    usage_seen: int | None = None

                    if compact:
                        event_stream = session_manager.yield_sandbox_compact_events(
                            sandbox.id,
                            session_id,
                            should_interrupt=interrupt_requested,
                            should_abort_on_teardown=lambda: not ownership_lost,
                        )
                    else:
                        event_stream = session_manager.yield_sandbox_events(
                            sandbox.id,
                            session_id,
                            current_prompt,
                            attachments=prompt_attachments,
                            should_interrupt=interrupt_requested,
                            should_abort_on_teardown=lambda: not ownership_lost,
                            # Job-kernel turns carry recalled memories in
                            # their host brief already.
                            skip_memory_recall=job_id is not None,
                            purpose=(
                                RuntimePurpose.SUBAGENT
                                if job_id is not None
                                else RuntimePurpose.CHAT
                            ),
                            requested_runtime=(
                                turn_state.requested_runtime
                                if turn_state is not None
                                else None
                            ),
                        )

                    for sandbox_event in event_stream:
                        if time.monotonic() > deadline:
                            deadline_exceeded = True
                        if deadline_exceeded:
                            continue

                        if not touch_turn(
                            cache=cache, turn_id=turn_id, runner_id=runner_id
                        ):
                            logger.info(
                                "Interactive turn %s runner ownership lost", turn_id
                            )
                            ownership_lost = True
                            ownership_lost_for_continue = True
                            return _PromptResult(_PromptOutcome.TERMINATED)
                        slot.extend()
                        if slot.lost:
                            ownership_lost = True
                            session_manager.finalize_persist(session_id, state)
                            db_session.commit()
                            persist_turn_error(
                                "This turn was interrupted and could not finish."
                            )
                            finish_turn(
                                cache=cache,
                                turn_id=turn_id,
                                status=TURN_STATUS_FAILED,
                                error_detail="Prompt slot lease lost mid-turn.",
                                runner_id=runner_id,
                            )
                            return _PromptResult(_PromptOutcome.TERMINATED)
                        if lease_lost.is_set():
                            # The job lease is gone: this turn no longer owns the
                            # job's state, so stop without continuing the job.
                            ownership_lost = True
                            ownership_lost_for_continue = True
                            session_manager.finalize_persist(session_id, state)
                            db_session.commit()
                            persist_turn_error(
                                "The job lease was lost mid-turn, so this step "
                                "was stopped. Send a follow-up message to continue."
                            )
                            finish_turn(
                                cache=cache,
                                turn_id=turn_id,
                                status=TURN_STATUS_FAILED,
                                error_detail="Job lease lost mid-turn.",
                                runner_id=runner_id,
                            )
                            turn_error_detail = "Job lease lost mid-turn."
                            return _PromptResult(_PromptOutcome.TERMINATED)
                        if isinstance(sandbox_event, SSEKeepalive):
                            continue

                        if isinstance(sandbox_event, ToolCallStart):
                            saw_tool_activity = True

                        # The transport already aborted the timed-out step and ends the
                        # stream after this event; drain it (don't return early, which
                        # would GeneratorExit and re-abort) and let the caller re-prompt.
                        if (
                            isinstance(sandbox_event, ActivityTimeoutError)
                            and can_continue
                        ):
                            timed_out = True
                            continue

                        session_manager.persist_sandbox_event(
                            session_id, state, sandbox_event
                        )
                        db_session.commit()

                        if isinstance(sandbox_event, SandboxError):
                            session_manager.finalize_persist(session_id, state)
                            db_session.commit()
                            persist_turn_error(sandbox_event.message)
                            finish_turn(
                                cache=cache,
                                turn_id=turn_id,
                                status=TURN_STATUS_FAILED,
                                error_detail=sandbox_event.message,
                                runner_id=runner_id,
                            )
                            turn_error_detail = sandbox_event.message
                            return _PromptResult(_PromptOutcome.TERMINATED)

                        if isinstance(sandbox_event, PromptResponse):
                            final_event_seen = True
                            stop_reason_seen = getattr(  # ods: ignore[getattr]
                                sandbox_event, "stop_reason", None
                            )
                            cancelled_event_seen = stop_reason_seen == "cancelled"

                        if isinstance(sandbox_event, ContextUsagePacket):
                            usage_seen = sandbox_event.used_tokens or None

                    if timed_out:
                        return _PromptResult(_PromptOutcome.TIMED_OUT)
                    return _PromptResult(
                        _PromptOutcome.COMPLETED,
                        final_event_seen=final_event_seen,
                        cancelled=cancelled_event_seen,
                        stop_reason=stop_reason_seen,
                        used_tokens=usage_seen,
                    )

                result = _PromptResult(_PromptOutcome.COMPLETED)
                if kind == "compact":
                    result = drive_one_prompt(
                        "",
                        [],
                        can_continue=False,
                        compact=True,
                    )
                else:
                    current_prompt = (
                        _skill_binding_preamble(selected_skill_ids, prompt) + prompt
                    )
                    for attempt in range(MAX_TIMEOUT_CONTINUATIONS + 1):
                        result = drive_one_prompt(
                            current_prompt,
                            attachments if attempt == 0 else [],
                            can_continue=attempt < MAX_TIMEOUT_CONTINUATIONS,
                        )
                        if result.outcome is _PromptOutcome.TIMED_OUT:
                            # Flush the aborted step's partial output as its own
                            # message so it can't merge with the continuation,
                            # then steer the agent.
                            session_manager.finalize_persist(session_id, state)
                            db_session.commit()
                            logger.info(
                                "Interactive turn %s step timed out; "
                                "re-prompting (%s/%s)",
                                turn_id,
                                attempt + 1,
                                MAX_TIMEOUT_CONTINUATIONS,
                            )
                            current_prompt = _TOOL_TIMEOUT_CONTINUATION_PROMPT
                            continue
                        if (
                            result.outcome is _PromptOutcome.COMPLETED
                            and result.stop_reason == "max_tokens"
                            and attempt < MAX_TIMEOUT_CONTINUATIONS
                        ):
                            # Output-token continuation: the reply was cut off
                            # by the length limit, not by choice. Flush the
                            # partial reply, then ask for the remainder.
                            session_manager.finalize_persist(session_id, state)
                            db_session.commit()
                            logger.info(
                                "Interactive turn %s hit the output limit; "
                                "continuing (%s/%s)",
                                turn_id,
                                attempt + 1,
                                MAX_TIMEOUT_CONTINUATIONS,
                            )
                            current_prompt = _MAX_TOKENS_CONTINUATION_PROMPT
                            continue
                        break

                if result.outcome is _PromptOutcome.TERMINATED:
                    if ownership_lost_for_continue:
                        skip_job_continue = True
                    return

                session_manager.finalize_persist(session_id, state)
                db_session.commit()

                # Without a tool call the workspace cannot have changed; the
                # tree walk (and the teardown snapshot it feeds) is pure cost.
                if saw_tool_activity:
                    from onyx.server.features.build.session.artifact_persist import (
                        persist_session_workspace_files,
                    )

                    persist_session_workspace_files(
                        db_session,
                        get_sandbox_manager(),
                        sandbox_id=sandbox.id,
                        session_id=session_id,
                        user_id=user_id,
                        turn_index=turn_index,
                    )

                if deadline_exceeded:
                    persist_turn_error(
                        "This turn was stopped after reaching its "
                        f"{max(1, round(budget_seconds / 60))}-minute time limit."
                    )
                    _record_failed_turn(runtime_choice.runtime_id, "deadline")
                    turn_error_detail = f"hard time cap exceeded ({budget_seconds}s)"
                    finish_turn(
                        cache=cache,
                        turn_id=turn_id,
                        status=TURN_STATUS_FAILED,
                        error_detail=turn_error_detail,
                        runner_id=runner_id,
                    )
                    return

                if not result.final_event_seen:
                    persist_turn_error(
                        "This turn ended before the agent returned a final response."
                    )
                    _record_failed_turn(runtime_choice.runtime_id, "no_final_event")
                    turn_error_detail = (
                        "Turn ended before opencode returned a final response."
                    )
                    finish_turn(
                        cache=cache,
                        turn_id=turn_id,
                        status=TURN_STATUS_FAILED,
                        error_detail=turn_error_detail,
                        runner_id=runner_id,
                    )
                    return

                if result.cancelled:
                    cancelled = True
                    _record_failed_turn(runtime_choice.runtime_id, "cancelled")
                    finish_turn(
                        cache=cache,
                        turn_id=turn_id,
                        status=TURN_STATUS_CANCELLED,
                        runner_id=runner_id,
                    )
                    return

                turn_succeeded = True
                from onyx.server.metrics.craft_sandbox import record_turn_outcome

                record_turn_outcome(runtime_choice.runtime_id, "succeeded")
                finish_turn(
                    cache=cache,
                    turn_id=turn_id,
                    status=TURN_STATUS_SUCCEEDED,
                    runner_id=runner_id,
                )
                if kind != "compact" and job_id is None:
                    # Extract user facts from user words only: job-kernel
                    # turns prompt with host briefs (qm: skip capture for
                    # autonomous actors).
                    from onyx.memory.long_term import maybe_retain_after_craft_turn

                    maybe_retain_after_craft_turn(
                        db_session,
                        user_id,
                        session_id,
                        prompt,
                        turn_index,
                    )
                    db_session.commit()
                    if kind == "prompt" and runtime_is_opencode:
                        # codex has no native compact; its replay budget
                        # shrinks at inject time instead.
                        _maybe_schedule_auto_compact(
                            cache=cache,
                            session=session,
                            used_tokens=result.used_tokens,
                            turn_index=turn_index,
                        )
            except Exception as exc:
                db_session.rollback()
                logger.exception("Interactive turn %s failed", turn_id)
                try:
                    session_manager.finalize_persist(session_id, state)
                    db_session.commit()
                    from onyx.server.features.build.session.artifact_persist import (
                        persist_session_workspace_files,
                    )

                    persist_session_workspace_files(
                        db_session,
                        get_sandbox_manager(),
                        sandbox_id=sandbox.id,
                        session_id=session_id,
                        user_id=user_id,
                        turn_index=turn_index,
                    )
                except Exception:
                    logger.exception(
                        "Failed to finalize persistence for turn %s", turn_id
                    )
                persist_turn_error("This turn failed unexpectedly.")
                turn_error_detail = f"{type(exc).__name__}: {str(exc)[:950]}"
                finish_turn(
                    cache=cache,
                    turn_id=turn_id,
                    status=TURN_STATUS_FAILED,
                    error_detail=turn_error_detail,
                    runner_id=runner_id,
                )
            finally:
                # True on every exit where this runner still owns the turn (normal
                # end, owned failure, cancel, exception); False once a successor
                # owns it (reclaim / slot-lost with a new turn). A successor sets
                # the active-turn pointer at creation, before it ever stamps, so
                # this guard clears our deadline exactly when no other turn's stamp
                # can be clobbered.
                try:
                    still_owns_turn = _can_clear_interrupt_fence(
                        cache=cache,
                        turn_id=turn_id,
                        session_id=session_id,
                        user_id=user_id,
                        runner_id=runner_id,
                    )
                except CACHE_TRANSIENT_ERRORS:
                    logger.warning(
                        "[SANDBOX-SERVE] interrupt-fence ownership check failed for session %s",
                        session_id,
                        exc_info=True,
                    )
                    still_owns_turn = False
                if still_owns_turn:
                    try:
                        clear_interrupt(session_id, cache)
                    except CACHE_TRANSIENT_ERRORS:
                        logger.warning(
                            "[SANDBOX-SERVE] failed to clear interrupt fence for session %s",
                            session_id,
                            exc_info=True,
                        )
                    session_manager.clear_turn_deadline(sandbox.id, session_id)
                prompt_slot_cm.__exit__(None, None, None)
    finally:
        # Turn-end fact for the tape, derived once here from the drive's
        # outcome variables instead of at each finish_turn call site. A
        # runner that dies before this note leaves the turn open on tape;
        # readers classify open turns as interrupted (dsh semantics).
        try:
            from onyx.server.features.build.sandbox.tape_recorder import (
                TURN_END_ABORTED,
                TURN_END_COMPLETED,
                TURN_END_DEADLINE,
                TURN_END_ERROR,
                TURN_END_INTERRUPTED,
                note_turn_end,
            )

            if turn_succeeded:
                reason = TURN_END_COMPLETED
            elif cancelled:
                reason = TURN_END_ABORTED
            elif deadline_exceeded:
                reason = TURN_END_DEADLINE
            elif turn_error_detail:
                reason = TURN_END_ERROR
            else:
                reason = TURN_END_INTERRUPTED
            note_turn_end(
                reason,
                detail=turn_error_detail if reason == TURN_END_ERROR else None,
            )
        except Exception:
            logger.debug("Tape turn/end note failed", exc_info=True)
        tape_stack.close()
        # request_skill links are filesystem-level (readable the same turn);
        # the harness catalog refreshes exactly once, after the turn ends —
        # disposing mid-turn would disturb the running prompt.
        try:
            from onyx.server.features.build.tools.implementations import (
                take_skill_catalog_dirty,
            )

            if sandbox_id is not None and take_skill_catalog_dirty(session_id):
                logger.info(
                    "Refreshing skill catalog after mid-turn request_skill "
                    "for session %s",
                    session_id,
                )
                get_sandbox_manager().dispose_opencode_instance(sandbox_id, session_id)
        except Exception:
            logger.warning(
                "Post-turn skill catalog refresh failed for %s",
                session_id,
                exc_info=True,
            )
        lease_stop.set()
        if sandbox_id is not None and not skip_job_continue:
            try:
                from onyx.server.features.build.jobs.continuation import (
                    maybe_continue_craft_job,
                )

                with get_session_with_current_tenant() as continue_session:
                    maybe_continue_craft_job(
                        continue_session,
                        session_id=session_id,
                        user_id=user_id,
                        sandbox_id=sandbox_id,
                        turn_succeeded=turn_succeeded,
                        deadline_exceeded=deadline_exceeded,
                        cancelled=cancelled,
                        lease_owner=str(turn_id) if job_id is not None else None,
                        turn_error_detail=turn_error_detail,
                    )
            except Exception:
                logger.exception("Failed to continue Craft job after turn %s", turn_id)
        if sandbox_id is not None:
            # After the continue decision: an enqueued successor turn makes the
            # active-turn check inside skip this, so a snapshot never races it.
            _snapshot_session_workspace_after_turn(
                sandbox_id=sandbox_id,
                session_id=session_id,
                user_id=user_id,
                tenant_id=get_current_tenant_id(),
                workspace_touched=saw_tool_activity,
            )
