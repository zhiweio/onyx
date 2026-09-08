"""Craft job kernel: one superstep after a worker turn or a host node."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_job import (
    add_specialist,
    advance_job_phase,
    count_open_specialists,
    mark_job_finished,
    mark_job_running,
    mark_job_waiting_lanes,
    specialists_all_terminal,
    specialists_any_failed,
)
from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus, SessionOrigin
from onyx.db.models import CraftJob
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
    INTERRUPT,
    LANE_END,
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
from onyx.server.features.build.jobs.plan import parse_plan_bytes
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
    job.state = state.model_dump(mode="json")
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


def initialize_job_state(job: CraftJob, *, goal: str) -> JobState:
    graph = compile_graph(str(job.domain))
    state = empty_state()
    state.goal = goal
    state.cursor = ["plan"]
    state.last_node = "plan"
    state.graph = graph.to_snapshot()
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
) -> None:
    """Run one superstep after an OpenCode turn on the parent session."""
    state = load_state(job)
    if _interrupt_if_unseen_question_timeout(db_session, job=job, state=state):
        return
    if lease_expired(job):
        state = _mark_drain(db_session, job=job, state=state, reason="lease_expired")
    graph = load_graph(job, state)
    node = _current_node(graph, state)
    if node is None:
        mark_job_finished(
            job, status=CraftJobStatus.FAILED, error_detail="Job has no current node"
        )
        _safe_commit(db_session)
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

    state = _commit_node_success(
        db_session,
        job=job,
        state=state,
        node=node,
        produced=produced,
        sandbox_id=sandbox_id,
        session_id=session_id,
    )
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


def after_lane_turn(
    db_session: Session,
    *,
    job: CraftJob,
    user_id: UUID,
    specialist_ok: bool,
    node_id: str | None,
) -> None:
    state = load_state(job)
    if _interrupt_if_unseen_question_timeout(db_session, job=job, state=state):
        return
    node = load_graph(job, state).get(node_id) if node_id else None
    if node_id and specialist_ok:
        specialist = next(
            (row for row in job.specialists if row.node_id == node_id),
            None,
        )
        try:
            sandbox_id = _sandbox_id_for_session(db_session, job.session_id, user_id)
        except Exception:
            sandbox_id = None
        if node is not None and sandbox_id is not None:
            lane_session = (
                specialist.session_id if specialist is not None else job.session_id
            )
            search_required = named_search_required(state.goal)
            gate = evaluate_contract_gate(
                sandbox_id=sandbox_id,
                session_id=job.session_id,
                node=node,
                deadline_exceeded=False,
                attempts=int(state.node_attempts.get(node.id) or 0),
                search_required=search_required,
            )
            if not gate.passed:
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
                    return
                if specialist is not None:
                    specialist.status = CraftJobSpecialistStatus.RUNNING
                    specialist.finished_at = None
                from onyx.server.features.build.jobs.continuation import (
                    enqueue_job_phase_turn,
                )

                enqueue_job_phase_turn(
                    db_session,
                    session_id=lane_session,
                    user_id=user_id,
                    prompt=retry_brief(
                        node.id,
                        gate.missing_paths(),
                        reasons=[item.reason for item in gate.missing],
                    ),
                )
                persist_state(job, state)
                _safe_commit(db_session)
                return
            missing_on_parent = _verify_lane_artifacts(
                sandbox_id=sandbox_id,
                session_id=job.session_id,
                paths=node.required_paths,
            )
            if missing_on_parent:
                emit(
                    db_session,
                    job_id=job.id,
                    event_type=GATE_FAIL,
                    payload={
                        "node_id": node.id,
                        "missing": missing_on_parent,
                    },
                )
                logger.error(
                    "Lane %s artifacts missing on shared outputs: %s",
                    node.id,
                    missing_on_parent,
                )
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
    if node_id:
        emit(
            db_session,
            job_id=job.id,
            event_type=LANE_END,
            payload={"node_id": node_id, "ok": specialist_ok},
        )
        notes_path = ""
        if node is not None and node.required_paths:
            notes_path = node.required_paths[0]
        _emit_lane_task_card(
            db_session,
            session_id=job.session_id,
            node_id=node_id,
            name=node.name if node is not None else node_id,
            status="completed" if specialist_ok else "failed",
            notes_path=notes_path,
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
    if specialists_any_failed(job) or not specialist_ok:
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="A specialist session failed",
        )
        _safe_commit(db_session)
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
) -> JobState:
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
        if plan_writes:
            writes.update(plan_writes)
    state = apply_writes(state, writes)
    if node.kind == "plan" and state.plan is not None:
        from onyx.server.features.build.jobs.plan import JobPlan

        try:
            plan = JobPlan.model_validate(
                {
                    "goal": state.plan.goal,
                    "phases": state.plan.phases,
                    "lanes": state.plan.lanes,
                    "inputs": state.plan.inputs,
                    "ask_delivery": state.plan.ask_delivery,
                    "done_when": state.plan.goal_done_when,
                }
            )
            graph = compile_graph(str(job.domain), plan)
            state = apply_writes(state, {"graph": graph.to_snapshot()})
        except Exception:
            logger.exception("Could not recompile graph from PLAN.json")
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
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail=gate_retry_limit_detail(gate, node.id),
        )
        _safe_commit(db_session)
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
        emit(
            db_session,
            job_id=job.id,
            event_type=DELIVERY,
            payload={"satisfied": True, "artifacts": list(state.artifacts)},
        )
        mark_job_finished(job, status=CraftJobStatus.SUCCEEDED)
        persist_state(job, state)
        _safe_commit(db_session)
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
    state = _commit_node_success(
        db_session,
        job=job,
        state=state,
        node=node,
        produced=produced,
        sandbox_id=sandbox_id,
        session_id=session_id,
    )
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
    prompt = assemble_brief(
        node=node,
        state=state,
        job_name=job.name,
        domain=job.domain,
        user_prompt=state.goal,
        missing=missing,
        snapshot=_job_snapshot(db_session, job, user_id),
        visible_tools=_visible_tools(db_session, user_id),
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
    from onyx.db.craft_project import create_project
    from onyx.server.features.build.configs import CRAFT_DEEP_JOB_MAX_SPECIALISTS
    from onyx.server.features.build.db.build_session import get_build_session
    from onyx.server.features.build.jobs.continuation import enqueue_job_phase_turn
    from onyx.server.features.build.session.manager import SessionManager

    open_count = count_open_specialists(job)
    if open_count + len(lanes) > CRAFT_DEEP_JOB_MAX_SPECIALISTS:
        mark_job_finished(
            job,
            status=CraftJobStatus.FAILED,
            error_detail="Too many research lanes for this job",
        )
        _safe_commit(db_session)
        return

    project_id = job.project_id
    if project_id is None:
        project = create_project(
            db_session, user=_user_stub(user_id), name=job.name[:128]
        )
        project_id = project.id
        job.project_id = project_id

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
        prompt = assemble_brief(
            node=node,
            state=state,
            job_name=job.name,
            domain=job.domain,
            user_prompt=state.goal,
            snapshot=_job_snapshot(db_session, job, user_id),
            visible_tools=_visible_tools(db_session, user_id),
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
    revised = _apply_review_revise(db_session, job=job, state=state, gate=gate)
    if revised is None:
        return False
    owner_id = gate.missing[0].owner_node if gate.missing else ""
    graph = load_graph(job, revised)
    owner = graph.get(owner_id) if owner_id else None
    if owner is None:
        for node_id in reversed(revised.completed_nodes):
            candidate = graph.get(node_id)
            if candidate is not None and candidate.kind != "review":
                owner = candidate
                break
    if owner is None:
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
            writes=writes,
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


def _emit_lane_task_card(
    db_session: Session,
    *,
    session_id: UUID,
    node_id: str,
    name: str,
    status: str,
    notes_path: str,
) -> None:
    from onyx.configs.constants import MessageType
    from onyx.server.features.build.db.build_session import (
        count_user_messages,
        create_message,
    )

    description = name
    if notes_path:
        description = f"{name} — {notes_path}"
    try:
        turn_index = count_user_messages(session_id, db_session)
        create_message(
            session_id=session_id,
            message_type=MessageType.ASSISTANT,
            turn_index=turn_index,
            message_metadata={
                "type": "assistant_message",
                "streamItems": [
                    {
                        "type": "tool_call",
                        "id": f"lane-task-{node_id}-{status}",
                        "toolCall": {
                            "id": f"lane-task-{node_id}-{status}",
                            "kind": "task",
                            "toolName": "task",
                            "title": name,
                            "description": description,
                            "command": "",
                            "status": status,
                            "rawOutput": notes_path,
                        },
                    }
                ],
            },
            db_session=db_session,
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

        surface = (
            [item.lower() for item in craft_mcp_tool_surface(db_session, user)]
            if user is not None
            else []
        )
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


def _visible_tools(db_session: Session, user_id: UUID) -> list[str]:
    try:
        from onyx.db.users import fetch_user_by_id
        from onyx.server.features.build.sandbox.util.mcp_config import (
            craft_mcp_tool_surface,
        )

        user = fetch_user_by_id(db_session, user_id)
        if user is None:
            return []
        return craft_mcp_tool_surface(db_session, user)
    except Exception:
        return []


def _lane_inactive_seconds(
    db_session: Session, specialist: Any, now: datetime
) -> float | None:
    stamp = getattr(specialist, "created_at", None)
    last_activity = None
    session_id = getattr(specialist, "session_id", None)
    if session_id is not None:
        try:
            from onyx.db.models import BuildSession

            row = db_session.get(BuildSession, session_id)
            last_activity = getattr(row, "last_activity_at", None) if row else None
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
    if job.status not in {
        CraftJobStatus.WAITING_LANES,
        CraftJobStatus.WAITING_SPECIALISTS,
    }:
        return False
    budget = max(int(job.phase_budget_seconds or 0), 1)
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
        after_lane_turn(
            db_session,
            job=job,
            user_id=user_id,
            specialist_ok=False,
            node_id=specialist.node_id,
        )
    if reaped:
        _safe_commit(db_session)
    return reaped


def _user_stub(user_id: UUID) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(id=user_id)
