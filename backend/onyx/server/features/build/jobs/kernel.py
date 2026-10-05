"""Craft job kernel: one superstep after a worker turn or a host node."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_job import (
    add_specialist,
    advance_job_phase,
    count_open_specialists,
    job_is_terminal,
    mark_job_finished,
    mark_job_running,
    mark_job_waiting_lanes,
    mark_specialist_finished,
    specialists_all_terminal,
    specialists_any_failed,
)
from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus, SessionOrigin
from onyx.db.models import CraftJob, CraftJobSpecialist
from onyx.server.features.build.jobs.assembler import assemble_brief
from onyx.server.features.build.jobs.blackboard import (
    merge_node_outputs,
    scan_artifacts,
)
from onyx.server.features.build.jobs.channels import (
    JobState,
    PlanChannel,
    apply_writes,
    empty_state,
    migrate_from_phases,
    strip_postgres_json_nuls,
)
from onyx.server.features.build.jobs.checkpoint import save_delta
from onyx.server.features.build.jobs.durability import (
    DurabilitySnapshot,
    load_durability_snapshot,
)
from onyx.server.features.build.jobs.gates import (
    ContractGateResult,
    evaluate_contract_gate,
    gate_retry_limit_detail,
    named_search_required,
    retry_brief,
    retry_limit_error_detail,
)
from onyx.server.features.build.jobs.graph import (
    GraphNode,
    JobGraph,
    compile_graph,
    graph_from_snapshot,
    is_lane_kind,
    ready_nodes,
)
from onyx.server.features.build.jobs.hooks import stop_gate
from onyx.server.features.build.jobs.host_workers import run_host_node
from onyx.server.features.build.jobs.journal import (
    DELIVERY,
    DRAIN,
    GATE_FAIL,
    GRAPH_WARNING,
    INTERRUPT,
    LANE_END,
    LANE_HEAL,
    LANE_RESPAWN,
    LANE_START,
    NODE_END,
    NODE_START,
    RESUME,
    RUN_START,
    emit,
)
from onyx.server.features.build.jobs.phase_gate import (
    DEFAULT_PHASE_RETRY_LIMIT,
    increment_gate_retries,
)
from onyx.server.features.build.jobs.plan import JobPlan, parse_plan_bytes
from onyx.server.features.build.jobs.turn_errors import is_transient_turn_error
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.utils.logger import setup_logger

logger = setup_logger()

LEASE_GRACE_SECONDS = 60


def _job_snapshot(
    db_session: Session, job: CraftJob, user_id: UUID
) -> DurabilitySnapshot:
    sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
    manager = None
    if sandbox_id is not None:
        try:
            manager = get_sandbox_manager()
        except Exception:
            manager = None
    return load_durability_snapshot(
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        manager=manager,
    )


def load_state(job: CraftJob) -> JobState:
    raw = _optional_dict(job, "state")
    if raw:
        return JobState.model_validate(raw)
    return migrate_from_phases(
        list(job.phases or []),
        int(job.current_phase_index or 0),
        domain=str(job.domain),
        goal=str(job.name or ""),
    )


def persist_state(job: CraftJob, state: JobState) -> None:
    job.state = strip_postgres_json_nuls(state.model_dump(mode="json"))
    graph = load_graph(job, state)
    completed = set(state.completed_nodes)
    phases = graph.to_phase_list(completed=list(completed))
    cursor = set(state.cursor)
    for index, phase in enumerate(phases):
        if phase["id"] in cursor:
            phase["status"] = "running"
            job.current_phase_index = index
        elif phase["id"] in completed:
            phase["status"] = "succeeded"
    job.phases = phases


def load_graph(job: CraftJob, state: JobState) -> JobGraph:
    snapshot = state.graph
    graph = graph_from_snapshot(snapshot) if snapshot else None
    if graph is not None:
        return graph
    return compile_graph(str(job.domain))


def initialize_job_state(
    job: CraftJob,
    *,
    goal: str,
    selected_skill_ids: Sequence[str] | None = None,
    plan: JobPlan | None = None,
) -> JobState:
    graph = compile_graph(str(job.domain), plan=plan)
    state = empty_state()
    state.goal = goal
    state.cursor = ["plan"]
    state.last_node = "plan"
    state.graph = graph.to_snapshot()
    state.selected_skill_ids = [str(item) for item in selected_skill_ids or []]
    persist_state(job, state)
    return state


def after_worker_turn(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    sandbox_id: UUID,
    session_id: UUID,
    deadline_exceeded: bool,
    lease_owner: str | None = None,
) -> None:
    """Run one superstep after an OpenCode turn on the parent session."""
    if job_is_terminal(job):
        return
    if lease_owner is not None and not lease_owned_by(job, lease_owner):
        logger.warning(
            "Job %s lease held by %s; losing turn %s skips its superstep",
            job.id,
            job.lease_owner,
            lease_owner,
        )
        return
    state = load_state(job)
    if _interrupt_if_unseen_question_timeout(db_session, job=job, state=state):
        return
    if lease_expired(job):
        state = _mark_drain(db_session, job=job, state=state, reason="lease_expired")
    graph = load_graph(job, state)
    node = _current_node(graph, state)
    if node is None:
        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail="Job has no current node",
        )
        return

    if deadline_exceeded:
        state = _mark_drain(db_session, job=job, state=state, reason="turn_deadline")

    produced = scan_artifacts(
        sandbox_id=sandbox_id, session_id=session_id, producer_node=node.id
    )
    attempts = int(state.node_attempts.get(node.id) or 0)
    gate = stop_gate(
        sandbox_id=sandbox_id,
        session_id=session_id,
        node=node,
        deadline_exceeded=deadline_exceeded,
        attempts=attempts,
        search_required=named_search_required(state.goal),
    )
    if not gate.passed:
        if node.kind == "review" and maybe_revise_after_review(
            db_session,
            job=job,
            user_id=user_id,
            state=state,
            node=node,
            gate=gate,
        ):
            return
        _fail_or_retry(
            db_session,
            job=job,
            user_id=user_id,
            state=state,
            node=node,
            gate=gate,
        )
        return

    committed = _commit_node_success(
        db_session,
        job=job,
        state=state,
        node=node,
        produced=produced,
        sandbox_id=sandbox_id,
        session_id=session_id,
    )
    if committed is None:
        # Plan gate already routed the failure to a retry.
        return
    state = committed
    _dispatch_next(
        db_session,
        job=job,
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=session_id,
        state=state,
    )


def resume_job(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    sandbox_id: UUID,
    action: str = "approve",
    note: str | None = None,
) -> None:
    state = load_state(job)
    if state.interrupt is None:
        return
    emit(
        db_session,
        job_id=job.id,
        event_type=RESUME,
        payload={"kind": state.interrupt.kind, "action": action},
    )
    resume_writes: dict[str, Any] = {"interrupt": None}
    if action == "approve":
        node_id = None
        if state.interrupt is not None:
            raw_node = state.interrupt.payload.get("node_id")
            if isinstance(raw_node, str) and raw_node.strip():
                node_id = raw_node.strip()
        if node_id:
            resume_writes["completed_nodes"] = [node_id]
    if action == "revise":
        resume_writes["reopen_nodes"] = list(state.completed_nodes) or ["plan"]
        resume_writes["cursor"] = []
        if note and note.strip():
            resume_writes["pending_enqueue"] = note.strip()
    if state.pause_started_at:
        try:
            pause_at = datetime.fromisoformat(state.pause_started_at)
        except ValueError:
            pause_at = None
        extra = 0.0
        if pause_at is not None:
            if pause_at.tzinfo is None:
                pause_at = pause_at.replace(tzinfo=timezone.utc)
            extra = max(0.0, (datetime.now(timezone.utc) - pause_at).total_seconds())
        resume_writes["paused_seconds"] = state.paused_seconds + extra
        resume_writes["pause_started_at"] = None
    state = apply_writes(state, resume_writes)
    mark_job_running(job)
    persist_state(job, state)
    _safe_commit(db_session)
    _dispatch_next(
        db_session,
        job=job,
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        state=state,
    )


def finalize_job_failure(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    error_detail: str,
) -> None:
    """Fail the job and settle everything it leaves open.

    Beyond the status write: still-open specialists go terminal (their lane
    cards settle to cancelled so none stay "in progress" forever), running
    lane turns get the interrupt fence, and the parent transcript gets a
    user-visible error row — without it the session shows a failed job with
    no explanation after reload.
    """
    mark_job_finished(
        job,
        status=CraftJobStatus.FAILED,
        error_detail=error_detail,
        db_session=db_session,
    )
    _notify_job_failed(job, error_detail=error_detail)
    open_rows = [
        row
        for row in job.specialists
        if row.status
        in (CraftJobSpecialistStatus.PENDING, CraftJobSpecialistStatus.RUNNING)
    ]
    for row in open_rows:
        mark_specialist_finished(
            row, status=CraftJobSpecialistStatus.FAILED, error_detail="Job failed"
        )
    if open_rows:
        from onyx.server.features.build.db.build_session import (
            settle_open_lane_task_cards,
        )

        settle_open_lane_task_cards(
            job.session_id,
            [row.node_id for row in open_rows if row.node_id],
            "cancelled",
            db_session,
        )
    _persist_job_failure_row(db_session, job=job, error_detail=error_detail)
    _safe_commit(db_session)

    if open_rows:
        from onyx.server.features.build.session.manager import SessionManager

        session_manager = SessionManager(db_session)
        for row in open_rows:
            try:
                session_manager.interrupt_message(row.session_id, user_id)
            except Exception:
                pass


def _persist_job_failure_row(
    db_session: Session, *, job: CraftJob, error_detail: str
) -> None:
    """One error build_message in the parent transcript summarizing the failure."""
    from onyx.configs.constants import MessageType
    from onyx.server.features.build.db.build_session import (
        count_user_messages,
        create_message,
    )

    failed = [
        row.node_id or "?"
        for row in job.specialists
        if row.status == CraftJobSpecialistStatus.FAILED
    ]
    summary = f"Long job failed: {error_detail}"
    if job.specialists:
        succeeded = sum(
            row.status == CraftJobSpecialistStatus.SUCCEEDED for row in job.specialists
        )
        failed_text = ", ".join(failed) if failed else "none"
        summary += (
            f" ({succeeded}/{len(job.specialists)} lanes succeeded;"
            f" failed: {failed_text})"
        )
    try:
        create_message(
            session_id=job.session_id,
            message_type=MessageType.ASSISTANT,
            turn_index=count_user_messages(job.session_id, db_session),
            message_metadata={
                "type": "error",
                "message": summary,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
            db_session=db_session,
        )
    except Exception:
        logger.warning(
            "Could not persist failure row for job %s", job.id, exc_info=True
        )


def after_lane_turn(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    specialist_ok: bool,
    node_id: str | None,
    lease_owner: str | None = None,
    turn_error_detail: str | None = None,
    specialist_session_id: UUID | None = None,
) -> None:
    """Settle one lane turn, then advance the job if this was the last lane.

    Per-lane settlement (card, journal, completed_nodes, artifacts) is NOT
    lease-gated: with N parallel lanes every running turn's heartbeat
    overwrites ``job.lease_owner``, so a lease check here would randomly drop
    completed_nodes writes and the kernel would re-spawn finished lanes. The
    lease only guards the job-wide superstep advance after all lanes are
    terminal. A per-job state lock serializes concurrent settlements because
    persist_state overwrites the whole state document.
    """
    if job_is_terminal(job):
        return
    # Serialize concurrent lane settlements: persist_state overwrites the
    # whole state document, so two interleaved settlements would lose writes.
    # Best-effort — without a cache (unit tests) settlement proceeds unlocked.
    state_lock = None
    try:
        from onyx.cache.factory import get_cache_backend

        state_lock = get_cache_backend().lock(f"craft:job:{job.id}:state", timeout=120)
        if not state_lock.acquire(blocking=True, blocking_timeout=15):
            state_lock = None
            logger.warning(
                "Could not lock job %s state; settling lane %s unlocked",
                job.id,
                node_id,
            )
    except Exception:
        state_lock = None
    try:
        _after_lane_turn_locked(
            db_session,
            job=job,
            user_id=user_id,
            specialist_ok=specialist_ok,
            node_id=node_id,
            lease_owner=lease_owner,
            turn_error_detail=turn_error_detail,
            specialist_session_id=specialist_session_id,
        )
    finally:
        if state_lock is not None:
            try:
                state_lock.release()
            except Exception:
                pass


def _after_lane_turn_locked(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    specialist_ok: bool,
    node_id: str | None,
    lease_owner: str | None = None,
    turn_error_detail: str | None = None,
    specialist_session_id: UUID | None = None,
) -> None:
    state = load_state(job)
    node = load_graph(job, state).get(node_id) if node_id else None
    if _interrupt_if_unseen_question_timeout(db_session, job=job, state=state):
        return
    specialist_row = _specialist_for_settlement(job, node_id, specialist_session_id)
    if node_id and not specialist_ok and node is not None:
        retried_state = _retry_failed_lane_if_transient(
            db_session,
            job=job,
            state=state,
            node=node,
            specialist=specialist_row,
            turn_error_detail=turn_error_detail,
            user_id=user_id,
        )
        if retried_state is not None:
            persist_state(job, retried_state)
            _safe_commit(db_session)
            return
    if node_id and specialist_ok:
        settled_state = _settle_successful_lane(
            db_session,
            job=job,
            state=state,
            node=node,
            specialist=specialist_row,
            user_id=user_id,
        )
        if settled_state is None:
            return
        state = settled_state
    if node_id:
        _emit_lane_settlement(
            db_session,
            job=job,
            node=node,
            node_id=node_id,
            ok=specialist_ok,
            specialist_row=specialist_row,
        )
        if specialist_ok:
            state = apply_writes(
                state, {"completed_nodes": [node_id], "last_node": node_id}
            )
        persist_state(job, state)
        _safe_commit(db_session)
        if specialist_ok:
            sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
            if sandbox_id is not None:
                _persist_job_workspace(
                    db_session,
                    user_id=user_id,
                    sandbox_id=sandbox_id,
                    session_id=job.session_id,
                )
    if job.status == CraftJobStatus.INTERRUPTED or state.interrupt is not None:
        return
    if not specialists_all_terminal(job):
        return
    # Only the advance is lease-gated; the last lane to finish is always the
    # most recent lease renewer (sibling heartbeats have stopped), so it wins.
    if lease_owner is not None and not lease_owned_by(job, lease_owner):
        logger.info(
            "Job %s lease held by %s; lane turn %s skips the superstep advance",
            job.id,
            job.lease_owner,
            lease_owner,
        )
        return
    if specialists_any_failed(job) or not specialist_ok:
        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail=_specialist_failure_detail(job),
        )
        return
    mark_job_running(job)
    persist_state(job, state)
    _safe_commit(db_session)
    sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
    if sandbox_id is None:
        return
    _dispatch_next(
        db_session,
        job=job,
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        state=state,
    )


def _specialist_for_settlement(
    job: CraftJob, node_id: str | None, session_id: UUID | None
) -> CraftJobSpecialist | None:
    """The specialist row this settlement is about.

    Matched by session when known (multi-round lanes have several rows per
    node); falls back to the newest row so a stale caller still settles.
    """
    if not node_id:
        return None
    rows = [row for row in job.specialists if row.node_id == node_id]
    if not rows:
        return None
    if session_id is not None:
        for row in rows:
            if row.session_id == session_id:
                return row
    return rows[-1]


def maybe_self_heal_job(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
) -> None:
    """Poll-time recovery for a job whose continuation was lost.

    A RUNNING/WAITING_LANES job with no open specialists, no active parent
    turn, and nothing pending to enqueue is idle by mistake — an exception
    swallowed mid-superstep left it without a driver. Re-dispatch the current
    node, rate-limited by a cache marker so polls cannot storm. Never raises:
    a failed heal leaves the next poll to try again.
    """
    try:
        if job_is_terminal(job) or job.status == CraftJobStatus.INTERRUPTED:
            return
        if job.status not in {
            CraftJobStatus.RUNNING,
            CraftJobStatus.WAITING_LANES,
        }:
            return
        if job.status == CraftJobStatus.WAITING_LANES:
            # Headless lane sessions have no SSE watcher, so nothing else
            # reaps a lane whose turn driver died with an API restart. A
            # settlement here retries or fails it and re-drives the job.
            if reap_inactive_lanes(db_session, job=job, user_id=user_id):
                return
        if count_open_specialists(job) > 0:
            return
        state = load_state(job)
        if state.pending_enqueue:
            return
        from onyx.server.features.build.jobs.protocol import current_phase

        raw_phase = current_phase(job.phases, job.current_phase_index)
        if raw_phase is not None and raw_phase.get("pending_enqueue_prompt"):
            return
        from onyx.cache.factory import get_cache_backend
        from onyx.server.features.build.interactive_turns.state import (
            get_active_turn,
        )

        cache = get_cache_backend()
        if get_active_turn(cache=cache, session_id=job.session_id, user_id=job.user_id):
            return
        marker = cache.lock(f"craft:job:{job.id}:selfheal", timeout=60)
        if not marker.acquire(blocking=False):
            return
        # Intentionally never released: expiry IS the cooldown.
        sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
        if sandbox_id is None:
            return
        logger.warning(
            "Self-healing idle craft job %s (status=%s, last_node=%s)",
            job.id,
            job.status,
            state.last_node,
        )
        mark_job_running(job)
        _safe_commit(db_session)
        _dispatch_next(
            db_session,
            job=job,
            user_id=user_id,
            sandbox_id=sandbox_id,
            session_id=job.session_id,
            state=load_state(job),
        )
    except Exception:
        logger.warning("Craft job self-heal failed for %s", job.id, exc_info=True)


def start_run_journal(db_session: Session, job: CraftJob) -> None:
    emit(
        db_session,
        job_id=job.id,
        event_type=RUN_START,
        payload={"domain": job.domain, "name": job.name},
    )


def apply_deep_job_sandbox_resources(db_session: Session, *, user_id: UUID) -> None:
    """Raise this user's sandbox to the deep-job CPU/memory profile."""
    sandbox_id = _sandbox_id_for_session(db_session, UUID(int=0), user_id)
    if sandbox_id is None:
        return
    try:
        get_sandbox_manager().apply_deep_job_resources(sandbox_id)
    except Exception:
        logger.exception("Could not apply deep-job sandbox resources")


def renew_lease(job: CraftJob, *, owner: str, seconds: int) -> None:
    now = datetime.now(timezone.utc)
    job.lease_owner = owner
    job.lease_expires_at = now + timedelta(
        seconds=max(seconds, 1) + LEASE_GRACE_SECONDS
    )


def lease_expired(job: CraftJob) -> bool:
    try:
        expires = job.lease_expires_at
    except AttributeError:
        return False
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires


def lease_owned_by(job: CraftJob, owner: str) -> bool:
    """Fence for turn-driven supersteps: only the lease holder may advance
    the job. Host-driven paths (resume, cancel) pass no owner and skip this."""
    try:
        return job.lease_owner == owner
    except AttributeError:
        return True


def _current_node(graph: JobGraph, state: JobState) -> GraphNode | None:
    if state.last_node:
        node = graph.get(state.last_node)
        if node is not None and node.id not in state.completed_nodes:
            return node
    for node_id in state.cursor:
        node = graph.get(node_id)
        if node is not None and node.id not in state.completed_nodes:
            return node
    ready = ready_nodes(graph, state)
    return ready[0] if ready else None


def _commit_node_success(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode,
    produced: dict[str, Any],
    sandbox_id: UUID,
    session_id: UUID,
) -> JobState | None:
    """Complete a node and persist its writes.

    Returns None when the node was NOT completed: for a plan node whose
    graph cannot be rebuilt the failure is routed to the gate-retry path
    instead — silently continuing on the old graph would ignore the
    model's plan (or a cycle would strand the job later)."""
    writes: dict[str, Any] = {
        "completed_nodes": [node.id],
        "last_node": node.id,
        "cursor": [],
        "budget": {"node_attempts": 1},
        "artifacts": merge_node_outputs(state, node, produced),
        "todo": {
            node.id: {
                "id": node.id,
                "owner_node": node.id,
                "status": "succeeded",
                "title": node.name,
            }
        },
    }
    if node.kind == "plan":
        plan_writes = _plan_from_disk(sandbox_id, session_id, state)
        if plan_writes is None:
            _fail_or_retry(
                db_session,
                job=job,
                user_id=job.user_id,
                state=state,
                node=node,
                gate=_invalid_plan_gate(node, "PLAN.json unreadable after gate"),
            )
            return None
        writes.update(plan_writes)
        rebuilt = _rebuild_graph_writes(
            db_session, job=job, state=state, node=node, plan_writes=plan_writes
        )
        if rebuilt is None:
            return None
        writes.update(rebuilt)
    state = apply_writes(state, writes)
    state = apply_writes(state, {"step": state.step + 1})
    persist_state(job, state)
    _checkpoint(db_session, job, state, writes, node.id)
    emit(
        db_session,
        job_id=job.id,
        event_type=NODE_END,
        payload={"node_id": node.id, "kind": node.kind},
    )
    if node.hitl in {"approve_plan", "approve_delivery", "clarify"}:
        interrupt_writes: dict[str, Any] = {
            "interrupt": {
                "kind": node.hitl,
                "payload": _interrupt_payload(state, node.hitl),
            }
        }
        if not state.pause_started_at:
            interrupt_writes["pause_started_at"] = datetime.now(
                timezone.utc
            ).isoformat()
        state = apply_writes(state, interrupt_writes)
        persist_state(job, state)
        job.status = CraftJobStatus.INTERRUPTED
        emit(
            db_session,
            job_id=job.id,
            event_type=INTERRUPT,
            payload={"kind": node.hitl},
        )
        _safe_commit(db_session)
    else:
        _safe_commit(db_session)
    return state


def _plan_from_disk(
    sandbox_id: UUID, session_id: UUID, state: JobState
) -> dict[str, Any] | None:
    try:
        raw = get_sandbox_manager().read_file(
            sandbox_id, session_id, "outputs/plan/PLAN.json"
        )
        plan = parse_plan_bytes(raw)
    except Exception:
        return None
    version = (state.plan.version + 1) if state.plan is not None else 1
    channel = PlanChannel.from_job_plan(plan, version=version)
    return {"plan": channel.model_dump(), "goal": plan.goal}


def _rebuild_graph_writes(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode,
    plan_writes: dict[str, Any],
) -> dict[str, Any] | None:
    """Compile the model's PLAN.json into a graph snapshot.

    Returns the graph write, or None when compilation failed (already
    routed to the plan gate retry — continuing on the previous graph would
    silently discard the model's schedule). Non-fatal warnings (dropped
    deps) are journaled, never silent."""
    from onyx.server.features.build.jobs.plan import JobPlan

    raw_plan = plan_writes.get("plan")
    if not isinstance(raw_plan, dict):
        _fail_or_retry(
            db_session,
            job=job,
            user_id=job.user_id,
            state=state,
            node=node,
            gate=_invalid_plan_gate(node, "plan channel missing"),
        )
        return None
    try:
        channel = PlanChannel.model_validate(raw_plan)
        plan = JobPlan.model_validate(
            {
                "goal": channel.goal,
                "phases": channel.phases,
                "lanes": channel.lanes,
                "inputs": channel.inputs,
                "ask_delivery": channel.ask_delivery,
                "done_when": channel.goal_done_when,
            }
        )
        graph = compile_graph(str(job.domain), plan)
    except Exception as exc:
        logger.warning("PLAN.json graph recompile failed: %s", exc)
        _fail_or_retry(
            db_session,
            job=job,
            user_id=job.user_id,
            state=state,
            node=node,
            gate=_invalid_plan_gate(node, str(exc)),
        )
        return None
    if graph.warnings:
        emit(
            db_session,
            job_id=job.id,
            event_type=GRAPH_WARNING,
            payload={"warnings": graph.warnings},
        )
    return {"graph": graph.to_snapshot()}


def _invalid_plan_gate(node: GraphNode | None, reason: str) -> ContractGateResult:
    from onyx.server.features.build.jobs.gates import GateMissing

    return ContractGateResult(
        passed=False,
        missing=[
            GateMissing(
                path="outputs/plan/PLAN.json",
                reason=f"plan graph invalid: {reason}"[:500],
                owner_node=node.id if node is not None else "plan",
            )
        ],
    )


def _fail_or_retry(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    state: JobState,
    node: GraphNode,
    gate: ContractGateResult,
) -> None:
    from onyx.server.features.build.jobs.continuation import _enqueue_or_remember

    attempts = int(state.node_attempts.get(node.id) or 0) + 1
    phase = _phase_dict(job, node.id)
    increment_gate_retries(phase)
    _replace_phase(job, node.id, phase)
    state = apply_writes(
        state,
        {
            "node_attempts": {node.id: attempts},
            "budget": {"node_attempts": 1},
            "todo": {
                node.id: {
                    "id": node.id,
                    "owner_node": node.id,
                    "status": "failed"
                    if attempts >= DEFAULT_PHASE_RETRY_LIMIT
                    else "running",
                    "blocking_reason": ", ".join(gate.missing_paths()),
                    "title": node.name,
                }
            },
        },
    )
    persist_state(job, state)
    emit(
        db_session,
        job_id=job.id,
        event_type=GATE_FAIL,
        payload={
            "node_id": node.id,
            "missing": [item.__dict__ for item in gate.missing],
            "attempts": attempts,
        },
    )
    if attempts >= DEFAULT_PHASE_RETRY_LIMIT:
        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail=gate_retry_limit_detail(gate, node.id),
        )
        return
    _safe_commit(db_session)
    prompt = retry_brief(
        node.id,
        gate.missing_paths(),
        reasons=[item.reason for item in gate.missing],
    )
    # Keep the legacy "not done" phrase so existing golden-path tests hold.
    prompt = f"Node `{node.id}` is not done. " + prompt.split(". ", 1)[-1]
    snapshot = _job_snapshot(db_session, job, user_id)
    if snapshot.files or snapshot.caches:
        prompt = prompt + "\n" + "\n".join(snapshot.format_for_brief())
    _enqueue_or_remember(
        db_session,
        job=job,
        user_id=user_id,
        phase=phase,
        prompt=prompt,
    )


def _dispatch_next(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    sandbox_id: UUID,
    session_id: UUID,
    state: JobState,
) -> None:
    if state.interrupt is not None:
        return
    graph = load_graph(job, state)
    ready = ready_nodes(graph, state)
    if not ready:
        completed = set(state.completed_nodes)
        incomplete = [node for node in graph.nodes if node.id not in completed]
        if incomplete:
            # No runnable node while work remains: the schedule is stalled
            # (cycle or unsatisfiable deps). Success here would be a lie.
            emit(
                db_session,
                job_id=job.id,
                event_type=DRAIN,
                payload={
                    "reason": "graph_stalled",
                    "incomplete_nodes": [node.id for node in incomplete],
                },
            )
            finalize_job_failure(
                db_session,
                job=job,
                user_id=user_id,
                error_detail=(
                    "Job graph stalled: no runnable node but "
                    f"{len(incomplete)} node(s) incomplete "
                    f"({', '.join(node.id for node in incomplete[:5])})"
                ),
            )
            return
        emit(
            db_session,
            job_id=job.id,
            event_type=DELIVERY,
            payload={"satisfied": True, "artifacts": list(state.artifacts)},
        )
        mark_job_finished(job, status=CraftJobStatus.SUCCEEDED)
        persist_state(job, state)
        _safe_commit(db_session)
        _notify_job_finished(job, artifact_count=len(state.artifacts))
        _persist_job_workspace(
            db_session,
            user_id=user_id,
            sandbox_id=sandbox_id,
            session_id=session_id,
        )
        return

    lanes = [node for node in ready if is_lane_kind(node.kind)]
    if lanes:
        _spawn_lanes(
            db_session,
            job=job,
            user_id=user_id,
            state=state,
            lanes=lanes,
        )
        return

    node = ready[0]
    if node.kind == "review":
        # Review may send work back to an owner node.
        pass
    if node.worker == "host_pure":
        _run_host_and_continue(
            db_session,
            job=job,
            user_id=user_id,
            sandbox_id=sandbox_id,
            session_id=session_id,
            state=state,
            node=node,
        )
        return
    _enqueue_node(db_session, job=job, user_id=user_id, state=state, node=node)


def _run_host_and_continue(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    sandbox_id: UUID,
    session_id: UUID,
    state: JobState,
    node: GraphNode,
) -> None:
    emit(
        db_session,
        job_id=job.id,
        event_type=NODE_START,
        payload={"node_id": node.id, "worker": "host_pure"},
    )
    graph = load_graph(job, state)
    lane_nodes = [item for item in graph.nodes if is_lane_kind(item.kind)]
    result = run_host_node(
        node=node,
        sandbox_id=sandbox_id,
        session_id=session_id,
        state=state,
        lane_nodes=lane_nodes,
    )
    if result.fallback_to_worker:
        _enqueue_node(db_session, job=job, user_id=user_id, state=state, node=node)
        return
    if not result.ok:
        gate = evaluate_contract_gate(
            sandbox_id=sandbox_id,
            session_id=session_id,
            node=node,
            deadline_exceeded=False,
            attempts=int(state.node_attempts.get(node.id) or 0),
        )
        _fail_or_retry(
            db_session,
            job=job,
            user_id=user_id,
            state=state,
            node=node,
            gate=gate,
        )
        return
    extra: dict[str, Any] = {}
    if result.payload and node.kind == "reconcile":
        extra["citations"] = result.payload.get("citations") or {}
        extra["conflicts"] = result.payload.get("conflicts") or []
    produced = scan_artifacts(
        sandbox_id=sandbox_id, session_id=session_id, producer_node=node.id
    )
    committed = _commit_node_success(
        db_session,
        job=job,
        state=state,
        node=node,
        produced=produced,
        sandbox_id=sandbox_id,
        session_id=session_id,
    )
    if committed is None:
        # Plan gate already routed the failure to a retry.
        return
    state = committed
    if extra:
        state = apply_writes(state, extra)
        persist_state(job, state)
        _safe_commit(db_session)
    _dispatch_next(
        db_session,
        job=job,
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=session_id,
        state=state,
    )


def _enqueue_node(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    state: JobState,
    node: GraphNode,
    missing: list[str] | None = None,
) -> None:
    from onyx.server.features.build.jobs.continuation import _enqueue_or_remember

    phase = _phase_dict(job, node.id)
    from onyx.memory.long_term import recall_texts_for_craft_job

    prompt = assemble_brief(
        node=node,
        state=state,
        job_name=job.name,
        domain=job.domain,
        user_prompt=state.goal,
        missing=missing,
        snapshot=_job_snapshot(db_session, job, user_id),
        visible_tools=_visible_tools(db_session, user_id, job),
        recalled_memories=recall_texts_for_craft_job(
            db_session,
            user_id,
            state.goal or job.name,
            project_id=job.project_id,
        ),
    )
    state = apply_writes(
        state,
        {
            "cursor": [node.id],
            "last_node": node.id,
            "pending_enqueue": None,
            "todo": {
                node.id: {
                    "id": node.id,
                    "owner_node": node.id,
                    "status": "running",
                    "title": node.name,
                }
            },
        },
    )
    persist_state(job, state)
    next_index = _phase_index(job, node.id)
    if next_index is not None:
        advance_job_phase(job, next_index)
    emit(
        db_session,
        job_id=job.id,
        event_type=NODE_START,
        payload={"node_id": node.id, "worker": "opencode_turn"},
    )
    _safe_commit(db_session)
    _enqueue_or_remember(
        db_session,
        job=job,
        user_id=user_id,
        phase=phase,
        prompt=prompt,
    )


def _spawn_lanes(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    state: JobState,
    lanes: list[GraphNode],
) -> None:
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_MAX_SPECIALISTS
    from onyx.server.features.build.db.build_session import get_build_session
    from onyx.server.features.build.jobs.continuation import enqueue_job_phase_turn
    from onyx.server.features.build.session.manager import SessionManager

    open_count = count_open_specialists(job)

    # A lane with a SUCCEEDED specialist whose deliverables still exist on the
    # shared outputs must never re-run: its completion was lost (historic
    # lease-race write loss), so heal the state instead of re-spawning.
    sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
    to_spawn: list[GraphNode] = []
    respawned: list[str] = []
    healed: list[str] = []
    for node in lanes:
        rows = [row for row in job.specialists if row.node_id == node.id]
        succeeded = any(
            row.status == CraftJobSpecialistStatus.SUCCEEDED for row in rows
        )
        if (
            succeeded
            and sandbox_id is not None
            and not _verify_lane_artifacts(
                sandbox_id=sandbox_id,
                session_id=job.session_id,
                paths=node.required_paths,
            )
        ):
            healed.append(node.id)
            continue
        to_spawn.append(node)
        if rows:
            respawned.append(node.id)
    if healed:
        state = apply_writes(state, {"completed_nodes": healed})
        for node_id in healed:
            emit(
                db_session,
                job_id=job.id,
                event_type=LANE_HEAL,
                payload={"node_id": node_id, "reason": "completed-missing"},
            )
        persist_state(job, state)
        _safe_commit(db_session)
        if not to_spawn:
            # Every ready lane was already done: advance instead of idling.
            if open_count == 0 and sandbox_id is not None:
                mark_job_running(job)
                _safe_commit(db_session)
                _dispatch_next(
                    db_session,
                    job=job,
                    user_id=user_id,
                    sandbox_id=sandbox_id,
                    session_id=job.session_id,
                    state=load_state(job),
                )
            return
        lanes = to_spawn

    for node_id in respawned:
        attempts = int(state.node_attempts.get(node_id) or 0) + 1
        state = apply_writes(state, {"node_attempts": {node_id: attempts}})
        emit(
            db_session,
            job_id=job.id,
            event_type=LANE_RESPAWN,
            payload={"node_id": node_id, "attempts": attempts},
        )
        if attempts >= DEFAULT_PHASE_RETRY_LIMIT:
            finalize_job_failure(
                db_session,
                job=job,
                user_id=user_id,
                error_detail=retry_limit_error_detail(
                    node_id, "lane kept re-running without completing"
                ),
            )
            return

    if open_count + len(lanes) > CRAFT_DEEP_JOB_MAX_SPECIALISTS:
        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail="Too many research lanes for this job",
        )
        return

    project_id = job.project_id

    session_manager = SessionManager(db_session)
    parent = get_build_session(job.session_id, user_id, db_session)
    scenario_id = job.scenario_id or (parent.scenario_id if parent else None)
    mark_job_waiting_lanes(job)
    state = apply_writes(
        state, {"cursor": [node.id for node in lanes], "last_node": lanes[0].id}
    )
    persist_state(job, state)
    _safe_commit(db_session)

    if _interrupt_if_named_mcp_unavailable(
        db_session, job=job, user_id=user_id, state=state
    ):
        return

    for node in lanes:
        build_session = session_manager.create_session(
            user_id,
            name=f"{job.name[:40]} / {node.role or node.id}"[:128],
            origin=SessionOrigin.JOB,
            scenario_id=scenario_id,
            project_id=project_id,
            headless=True,
            share_workspace_from=job.session_id,
        )
        from onyx.memory.long_term import recall_texts_for_craft_job

        prompt = assemble_brief(
            node=node,
            state=state,
            job_name=job.name,
            domain=job.domain,
            user_prompt=state.goal,
            snapshot=_job_snapshot(db_session, job, user_id),
            visible_tools=_visible_tools(db_session, user_id, job),
            recalled_memories=recall_texts_for_craft_job(
                db_session,
                user_id,
                state.goal or job.name,
                project_id=job.project_id,
            ),
        )
        add_specialist(
            db_session,
            job=job,
            session_id=build_session.id,
            role=(node.role or node.id)[:64],
            prompt=prompt,
            node_id=node.id,
            checkpoint_ns=f"node:{node.id}",
        )
        emit(
            db_session,
            job_id=job.id,
            event_type=LANE_START,
            payload={"node_id": node.id, "session_id": str(build_session.id)},
        )
        _emit_lane_task_card(
            db_session,
            session_id=job.session_id,
            node_id=node.id,
            name=node.name,
            status="in_progress",
            notes_path=node.required_paths[0] if node.required_paths else "",
            specialist_session_id=build_session.id,
            role=node.role,
            job_id=job.id,
        )
        enqueue_job_phase_turn(
            db_session,
            session_id=build_session.id,
            user_id=user_id,
            prompt=prompt,
        )
    _safe_commit(db_session)


def _apply_review_revise(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    gate: ContractGateResult,
) -> JobState | None:
    if gate.passed or not gate.missing:
        return None
    owner = gate.missing[0].owner_node
    state = apply_writes(
        state,
        {
            "reopen_nodes": [owner],
            "cursor": [owner],
            "last_node": owner,
            "conflicts": [
                {
                    "kind": "review",
                    "detail": item.reason,
                    "paths": [item.path],
                    "owner_node": item.owner_node,
                }
                for item in gate.missing
            ],
        },
    )
    persist_state(job, state)
    _safe_commit(db_session)
    return state


def _is_review_self_owner(owner: GraphNode, review_node: GraphNode) -> bool:
    return owner.id == review_node.id or owner.kind == "review"


def maybe_revise_after_review(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    state: JobState,
    node: GraphNode,
    gate: ContractGateResult,
) -> bool:
    if node.kind != "review" or gate.passed:
        return False
    owner_id = gate.missing[0].owner_node if gate.missing else ""
    graph = load_graph(job, state)
    owner = graph.get(owner_id) if owner_id else None
    # Review may reopen compose/derive/evidence. Re-enqueueing the reviewer
    # itself bypasses node_attempts and loops forever.
    if owner is not None and _is_review_self_owner(owner, node):
        return False
    if owner is None:
        for node_id in reversed(state.completed_nodes):
            candidate = graph.get(node_id)
            if candidate is not None and not _is_review_self_owner(candidate, node):
                owner = candidate
                break
    if owner is None or _is_review_self_owner(owner, node):
        return False
    revised = _apply_review_revise(db_session, job=job, state=state, gate=gate)
    if revised is None:
        return False
    _enqueue_node(
        db_session,
        job=job,
        user_id=user_id,
        state=revised,
        node=owner,
        missing=gate.missing_paths(),
    )
    return True


def _mark_drain(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    reason: str,
) -> JobState:
    job.drain_reason = reason
    emit(
        db_session,
        job_id=job.id,
        event_type=DRAIN,
        payload={"reason": reason, "node_id": state.last_node},
    )
    return apply_writes(state, {"drain_reason": reason})


def _checkpoint(
    db_session: Session,
    job: CraftJob,
    state: JobState,
    writes: dict[str, Any],
    node_id: str,
) -> None:
    try:
        save_delta(
            db_session,
            job_id=job.id,
            ns=f"node:{node_id}",
            step=state.step,
            writes=strip_postgres_json_nuls(writes),
        )
    except Exception:
        logger.exception("Could not write job checkpoint")


def _phase_dict(job: CraftJob, node_id: str) -> dict[str, Any]:
    for phase in job.phases or []:
        if str(phase.get("id") or "") == node_id:
            return dict(phase)
    return {"id": node_id, "name": node_id, "kind": node_id, "status": "running"}


def _phase_index(job: CraftJob, node_id: str) -> int | None:
    for index, phase in enumerate(job.phases or []):
        if str(phase.get("id") or "") == node_id:
            return index
    return None


def _replace_phase(job: CraftJob, node_id: str, phase: dict[str, Any]) -> None:
    updated = list(job.phases or [])
    for index, existing in enumerate(updated):
        if str(existing.get("id") or "") == node_id:
            updated[index] = dict(phase)
            job.phases = updated
            return
    updated.append(dict(phase))
    job.phases = updated


def _optional_dict(job: CraftJob, name: str) -> dict[str, Any] | None:
    try:
        raw = job.state if name == "state" else None
    except AttributeError:
        return None
    return raw if isinstance(raw, dict) and raw else None


def _safe_commit(db_session: Session) -> None:
    try:
        db_session.commit()
    except AttributeError:
        return


def _retry_lane_or_fail(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode,
    missing: list[str],
    reasons: list[str],
    specialist: CraftJobSpecialist | None,
    lane_session: UUID,
    user_id: UUID,
) -> JobState:
    """Retry a failed lane turn, failing the job once attempts hit the limit.

    Mirrors ``_fail_or_retry`` for the worker path: attempts accumulate in
    ``node_attempts`` so a lane cannot retry forever.
    """
    attempts = int(state.node_attempts.get(node.id) or 0) + 1
    state = apply_writes(
        state,
        {
            "node_attempts": {node.id: attempts},
            "budget": {"node_attempts": 1},
        },
    )
    emit(
        db_session,
        job_id=job.id,
        event_type=GATE_FAIL,
        payload={
            "node_id": node.id,
            "missing": missing,
            "attempts": attempts,
        },
    )
    if attempts >= DEFAULT_PHASE_RETRY_LIMIT:
        finalize_job_failure(
            db_session,
            job=job,
            user_id=user_id,
            error_detail=retry_limit_error_detail(node.id, *reasons),
        )
        return state
    if specialist is not None:
        specialist.status = CraftJobSpecialistStatus.RUNNING
        specialist.finished_at = None
    from onyx.server.features.build.jobs.continuation import enqueue_job_phase_turn

    enqueue_job_phase_turn(
        db_session,
        session_id=lane_session,
        user_id=user_id,
        prompt=retry_brief(node.id, missing, reasons=reasons),
    )
    return state


def _verify_lane_artifacts(
    *,
    sandbox_id: UUID,
    session_id: UUID,
    paths: list[str],
) -> list[str]:
    manager = get_sandbox_manager()
    missing: list[str] = []
    for path in paths:
        try:
            raw = manager.read_file(sandbox_id, session_id, path)
        except Exception:
            missing.append(path)
            continue
        if not isinstance(raw, (bytes, bytearray)) or not raw.strip():
            missing.append(path)
    return missing


def _is_search_unavailable_gate(gate: ContractGateResult) -> bool:
    return any(
        "citation" in item.reason or "search" in item.reason.lower()
        for item in gate.missing
    )


def _interrupt_for_choice(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    summary: str,
    steps: list[str],
    node_id: str | None = None,
) -> JobState:
    payload: dict[str, Any] = {
        "goal": state.goal,
        "summary": summary,
        "steps": steps,
    }
    if node_id:
        payload["node_id"] = node_id
    writes: dict[str, Any] = {
        "interrupt": {
            "kind": "clarify",
            "payload": payload,
        }
    }
    if not state.pause_started_at:
        writes["pause_started_at"] = datetime.now(timezone.utc).isoformat()
    next_state = apply_writes(state, writes)
    persist_state(job, next_state)
    job.status = CraftJobStatus.INTERRUPTED
    emit(
        db_session,
        job_id=job.id,
        event_type=INTERRUPT,
        payload={"kind": "clarify", "summary": summary},
    )
    return next_state


def _settle_successful_lane(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode | None,
    specialist: CraftJobSpecialist | None,
    user_id: UUID,
) -> JobState | None:
    """Gate-check a succeeded lane and collect its shared outputs.

    Returns the updated state, or None when the lane was interrupted or
    re-enqueued for a retry (both already persisted; the caller stops).
    """
    try:
        sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
    except Exception:
        sandbox_id = None
    if node is None or sandbox_id is None:
        return state
    lane_session = specialist.session_id if specialist is not None else job.session_id
    gate = evaluate_contract_gate(
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        node=node,
        deadline_exceeded=False,
        attempts=int(state.node_attempts.get(node.id) or 0),
        search_required=named_search_required(state.goal),
    )
    if not gate.passed:
        return _gate_failed_lane(
            db_session,
            job=job,
            state=state,
            node=node,
            gate=gate,
            specialist=specialist,
            lane_session=lane_session,
            user_id=user_id,
        )
    missing_on_parent = _verify_lane_artifacts(
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        paths=node.required_paths,
    )
    if missing_on_parent:
        logger.error(
            "Lane %s artifacts missing on shared outputs: %s",
            node.id,
            missing_on_parent,
        )
        state = _retry_lane_or_fail(
            db_session,
            job=job,
            state=state,
            node=node,
            missing=missing_on_parent,
            reasons=[
                f"lane artifact missing on shared outputs: {path}"
                for path in missing_on_parent
            ],
            specialist=specialist,
            lane_session=lane_session,
            user_id=user_id,
        )
        persist_state(job, state)
        _safe_commit(db_session)
        return None
    produced = scan_artifacts(
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        producer_node=node.id,
    )
    state = apply_writes(
        state, {"artifacts": merge_node_outputs(state, node, produced)}
    )
    artifact_ids = [
        path
        for path in node.required_paths
        if path in produced or path in state.artifacts
    ]
    if specialist is not None:
        specialist.output_artifact_ids = artifact_ids
    return state


def _gate_failed_lane(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode,
    gate: ContractGateResult,
    specialist: CraftJobSpecialist | None,
    lane_session: UUID,
    user_id: UUID,
) -> JobState | None:
    if _is_search_unavailable_gate(gate):
        state = _interrupt_for_choice(
            db_session,
            job=job,
            state=state,
            summary="Search is not available. Retry, use existing tools, or cancel.",
            steps=["Retry search", "Use existing tools", "Cancel"],
            node_id=node.id,
        )
        persist_state(job, state)
        _safe_commit(db_session)
        return None
    state = _retry_lane_or_fail(
        db_session,
        job=job,
        state=state,
        node=node,
        missing=gate.missing_paths(),
        reasons=[item.reason for item in gate.missing],
        specialist=specialist,
        lane_session=lane_session,
        user_id=user_id,
    )
    persist_state(job, state)
    _safe_commit(db_session)
    return None


def _retry_failed_lane_if_transient(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
    node: GraphNode,
    specialist: CraftJobSpecialist | None,
    turn_error_detail: str | None,
    user_id: UUID,
) -> JobState | None:
    """Retry a failed lane turn whose cause is transient (hard cap mid-work,
    upstream LLM blip, transport hiccup) instead of failing the whole job.

    Returns the updated state when a retry was scheduled, None when the
    failure stands (non-transient cause).
    """
    if not is_transient_turn_error(turn_error_detail):
        return None
    lane_session = specialist.session_id if specialist is not None else job.session_id
    return _retry_lane_or_fail(
        db_session,
        job=job,
        state=state,
        node=node,
        missing=list(node.required_paths) or ["this lane's contract"],
        reasons=[turn_error_detail or "lane turn failed"],
        specialist=specialist,
        lane_session=lane_session,
        user_id=user_id,
    )


def _emit_lane_settlement(
    db_session: Session,
    *,
    job: CraftJob,
    node: GraphNode | None,
    node_id: str,
    ok: bool,
    specialist_row: CraftJobSpecialist | None = None,
) -> None:
    """Journal lane.end plus the parent-transcript lane card, terminal status."""
    emit(
        db_session,
        job_id=job.id,
        event_type=LANE_END,
        payload={"node_id": node_id, "ok": ok},
    )
    notes_path = ""
    if node is not None and node.required_paths:
        notes_path = node.required_paths[0]
    _emit_lane_task_card(
        db_session,
        session_id=job.session_id,
        node_id=node_id,
        name=node.name if node is not None else node_id,
        status="completed" if ok else "failed",
        notes_path=notes_path,
        specialist_session_id=(
            specialist_row.session_id if specialist_row is not None else None
        ),
        role=(
            specialist_row.role
            if specialist_row is not None
            else (node.role if node is not None else None)
        ),
        job_id=job.id,
    )


def _specialist_failure_detail(job: CraftJob) -> str:
    failed = [
        f"{row.node_id} ({row.error_detail or 'turn failed'})"
        for row in job.specialists
        if row.status == CraftJobSpecialistStatus.FAILED
    ]
    if not failed:
        return "A specialist session failed"
    detail = "; ".join(failed)
    return f"A specialist session failed: {detail}"


def _emit_lane_task_card(
    db_session: Session,
    *,
    session_id: UUID,
    node_id: str,
    name: str,
    status: str,
    notes_path: str,
    specialist_session_id: UUID | None = None,
    role: str | None = None,
    job_id: UUID | None = None,
) -> None:
    from onyx.server.features.build.db.build_session import upsert_lane_task_message
    from onyx.server.features.build.jobs.lane_task import lane_task_card_metadata

    try:
        upsert_lane_task_message(
            session_id,
            node_id,
            lane_task_card_metadata(
                node_id=node_id,
                name=name,
                status=status,
                notes_path=notes_path,
                specialist_session_id=specialist_session_id,
                role=role,
                job_id=job_id,
            ),
            db_session,
        )
    except Exception:
        logger.exception("Could not persist lane task card for %s", node_id)


def _persist_job_workspace(
    db_session: Session,
    *,
    user_id: UUID,
    sandbox_id: UUID,
    session_id: UUID,
) -> None:
    """Archive the session tree after a lane or job finishes."""
    try:
        from onyx.server.features.build.session.artifact_persist import (
            persist_session_workspace_files,
        )

        persist_session_workspace_files(
            db_session,
            get_sandbox_manager(),
            sandbox_id=sandbox_id,
            session_id=session_id,
            user_id=user_id,
        )
    except Exception:
        logger.exception("Could not persist workspace for session %s", session_id)


def _sandbox_id_for_session(
    db_session: Session, _session_id: UUID, user_id: UUID
) -> UUID | None:
    try:
        from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id

        sandbox = get_sandbox_by_user_id(db_session, user_id)
    except Exception:
        return None
    if sandbox is None:
        return None
    return sandbox.id


def _interrupt_payload(state: JobState, kind: str) -> dict[str, Any]:
    steps: list[str] = []
    if state.plan is not None:
        for phase in state.plan.phases:
            name = str(phase.get("name") or phase.get("id") or "").strip()
            if name and name.lower() != "plan":
                steps.append(name)
        for lane in state.plan.lanes:
            role = str(lane.get("role") or "").strip()
            if role:
                steps.append(role)
    goal = state.goal.strip()
    if kind == "approve_delivery":
        summary = f"Review the result for: {goal}" if goal else "Review the result."
    elif kind == "clarify":
        summary = f"Need a choice to continue: {goal}" if goal else "Need a choice."
    elif steps:
        summary = f"Proposed next steps for: {goal}" if goal else "Proposed next steps."
    else:
        summary = f"Ready to start: {goal}" if goal else "Ready to start."
    return {"goal": goal, "summary": summary, "steps": steps}


def _interrupt_if_unseen_question_timeout(
    db_session: Session,
    *,
    job: CraftJob,
    state: JobState,
) -> bool:
    try:
        from onyx.cache.factory import get_cache_backend
        from onyx.server.features.build import question_ask
        from shared_configs.contextvars import get_current_tenant_id

        cache = get_cache_backend(tenant_id=get_current_tenant_id())
        if not question_ask.take_unseen_timeout(str(job.session_id), cache):
            return False
    except Exception:
        return False
    _interrupt_for_choice(
        db_session,
        job=job,
        state=state,
        summary="A question timed out before it was shown. Choose how to continue.",
        steps=["Retry the question", "Continue without it", "Cancel"],
    )
    _safe_commit(db_session)
    return True


def _interrupt_if_named_mcp_unavailable(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    state: JobState,
) -> bool:
    if not named_search_required(state.goal):
        return False
    try:
        from onyx.db.users import fetch_user_by_id
        from onyx.server.features.build.sandbox.util.mcp_config import (
            craft_mcp_tool_surface,
        )

        user = fetch_user_by_id(db_session, user_id)

        if user is None:
            surface = []
        else:
            from onyx.server.features.build.jobs.mcp import resolve_job_mcp_server_ids

            surface = [
                item.lower()
                for item in craft_mcp_tool_surface(
                    db_session,
                    user,
                    allowed_server_ids=resolve_job_mcp_server_ids(
                        db_session, user, job
                    ),
                )
            ]
    except Exception:
        surface = []
    goal = state.goal.lower()
    wanted: list[str] = []
    if "parallel" in goal:
        wanted.append("parallel")
    if "tavily" in goal:
        wanted.append("tavily")
    if "exa" in goal:
        wanted.append("exa")
    missing = [name for name in wanted if not any(name in item for item in surface)]
    if not missing:
        return False
    _interrupt_for_choice(
        db_session,
        job=job,
        state=state,
        summary=(
            f"Named search tool ({', '.join(missing)}) is not available. "
            "Retry, use existing tools, or cancel."
        ),
        steps=["Retry search", "Use existing tools", "Cancel"],
    )
    _safe_commit(db_session)
    return True


def _visible_tools(
    db_session: Session, user_id: UUID, job: CraftJob | None = None
) -> list[str]:
    try:
        from onyx.db.users import fetch_user_by_id
        from onyx.server.features.build.jobs.mcp import resolve_job_mcp_server_ids
        from onyx.server.features.build.sandbox.util.mcp_config import (
            craft_mcp_tool_surface,
        )

        user = fetch_user_by_id(db_session, user_id)
        if user is None:
            return []
        allowed = (
            resolve_job_mcp_server_ids(db_session, user, job)
            if job is not None
            else None
        )
        return craft_mcp_tool_surface(db_session, user, allowed_server_ids=allowed)
    except Exception:
        return []


def _lane_inactive_seconds(
    db_session: Session, specialist: Any, now: datetime
) -> float | None:
    # specialist rows arrive duck-typed from callers; access is best-effort.
    stamp = getattr(specialist, "created_at", None)  # ods: ignore[getattr]
    last_activity = None
    session_id = getattr(specialist, "session_id", None)  # ods: ignore[getattr]
    if session_id is not None:
        try:
            from onyx.db.models import BuildSession

            row = db_session.get(BuildSession, session_id)
            last_activity = (
                getattr(row, "last_activity_at", None)  # ods: ignore[getattr]
                if row
                else None
            )
        except Exception:
            last_activity = None
    ref = last_activity or stamp
    if ref is None:
        return None
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (now - ref).total_seconds()


def reap_inactive_lanes(db_session: Session, *, job: CraftJob, user_id: UUID) -> bool:
    """Fail RUNNING specialists that sat past the phase budget with no activity."""
    if job.status not in {CraftJobStatus.WAITING_LANES}:
        return False
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_PHASE_BUDGET_SECONDS

    # A null/zero budget must not degenerate into an instant reap: a lane
    # whose turn started seconds ago is alive even with no budget recorded.
    budget = max(
        int(job.phase_budget_seconds or CRAFT_DEEP_JOB_PHASE_BUDGET_SECONDS), 1
    )
    now = datetime.now(timezone.utc)
    reaped = False
    from onyx.db.craft_job import mark_specialist_finished

    for specialist in list(job.specialists or []):
        if specialist.status != CraftJobSpecialistStatus.RUNNING:
            continue
        age = _lane_inactive_seconds(db_session, specialist, now)
        if age is None or age < budget:
            continue
        mark_specialist_finished(
            specialist,
            status=CraftJobSpecialistStatus.FAILED,
            error_detail="Lane inactive",
        )
        reaped = True
        # The detail carries the transient marker ("lane inactive"), so the
        # settlement retries the lane once instead of failing the job.
        after_lane_turn(
            db_session,
            job=job,
            user_id=user_id,
            specialist_ok=False,
            node_id=specialist.node_id,
            turn_error_detail="Lane inactive: turn driver was lost",
            specialist_session_id=specialist.session_id,
        )
    if reaped:
        _safe_commit(db_session)
    return reaped


def _job_im_link(job: CraftJob) -> tuple[str, str]:
    """(full URL, scenario display name) for job notifications."""
    from onyx.configs.app_configs import WEB_DOMAIN
    from onyx.onyxbot.china.scenario_trigger import im_job_display_name

    url = f"{WEB_DOMAIN}/craft/v1?sessionId={job.session_id}"
    return url, im_job_display_name(job.name)


def _notify_job_finished(job: CraftJob, *, artifact_count: int) -> None:
    """Best-effort IM push to the job owner when a job succeeds.

    In-app notifications stay the durable channel; this is the reach
    channel for owners with a China IM binding (scenario runs launched
    from IM land back in the same chat)."""
    try:
        from onyx.onyxbot.china.framework import dispatch_im_notification

        url, display = _job_im_link(job)
        dispatch_im_notification(
            user_id=job.user_id,
            title=f"✅ 场景任务完成:{display}",
            description=(
                f"产出 {artifact_count} 个文件。"
                f"[打开任务]({url})\nsessionId: {job.session_id}"
            ),
            link=url,
        )
    except Exception:
        logger.warning("job-finished IM push failed", exc_info=True)


def _notify_job_failed(job: CraftJob, *, error_detail: str) -> None:
    """Best-effort IM push when a job fails — IM users have no other way
    to learn a run ended (and that their job slot freed up)."""
    try:
        from onyx.onyxbot.china.framework import dispatch_im_notification

        url, display = _job_im_link(job)
        reason = (error_detail or "").strip()
        description = f"[打开任务]({url})\nsessionId: {job.session_id}"
        if reason:
            description = f"{reason[:200]}\n{description}"
        dispatch_im_notification(
            user_id=job.user_id,
            title=f"❌ 场景任务失败:{display}",
            description=description,
            link=url,
        )
    except Exception:
        logger.warning("job-failed IM push failed", exc_info=True)
