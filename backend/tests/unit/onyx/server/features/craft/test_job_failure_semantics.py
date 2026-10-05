"""Failure semantics for craft long jobs.

Covers the 2daf1bda incident class: hard-capped lane turns, lanes mislabeled
failed because a sibling failed, lease-lost lanes stuck "in progress",
missing parent-transcript failure rows, and the skill-binding briefs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Final, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import BuildMessage, CraftJob
from onyx.server.features.build.interactive_turns.executor import (
    _skill_binding_preamble,
)
from onyx.server.features.build.jobs.assembler import assemble_brief
from onyx.server.features.build.jobs.channels import empty_state
from onyx.server.features.build.jobs.continuation import job_turn_budgets
from onyx.server.features.build.jobs.graph import compile_graph
from onyx.server.features.build.jobs.kernel import (
    after_lane_turn,
    finalize_job_failure,
    initialize_job_state,
    load_state,
    persist_state,
)
from onyx.server.features.build.jobs.plan import parse_plan
from onyx.server.features.build.jobs.turn_errors import is_transient_turn_error
from onyx.server.features.build.timeouts import (
    INTERACTIVE_TURN_HARD_CAP_SECONDS,
    SCHEDULED_RUN_HARD_CAP_SECONDS,
)


def _job(domain: str = "tax", **kwargs):
    graph = compile_graph(domain)
    values: dict[str, Any] = {
        "id": uuid4(),
        "session_id": uuid4(),
        "domain": domain,
        "name": "kernel",
        "status": CraftJobStatus.RUNNING,
        "phases": graph.to_phase_list(),
        "current_phase_index": 0,
        "state": {},
        "started_at": None,
        "total_budget_seconds": 7200,
        "phase_budget_seconds": 1500,
        "error_detail": None,
        "specialists": [],
        "project_id": uuid4(),
        "scenario_id": None,
    }
    values.update(kwargs)
    job = cast(CraftJob, SimpleNamespace(**values))
    initialize_job_state(job, goal="goal")
    return job


class _NoRowsQuery:
    def filter(self, *_args: object, **_kwargs: object) -> "_NoRowsQuery":
        return self

    def first(self) -> None:
        return None

    def all(self) -> list[object]:
        return []

    def count(self) -> int:
        return 0


class _StubSessionManager:
    def __init__(self, *_a: object, **_k: object) -> None:
        pass

    def interrupt_message(self, *_a: object, **_k: object) -> bool:
        return True


class _RecordingDb:
    """Fake session that records every added row for assertions."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def refresh(self, *_a: object, **_k: object) -> None:
        return None

    def query(self, *_a: object, **_k: object) -> _NoRowsQuery:
        return _NoRowsQuery()

    def scalars(self, *_a: object, **_k: object) -> _NoRowsQuery:
        return _NoRowsQuery()

    def execute(self, *_a: object, **_k: object) -> _NoRowsQuery:
        return _NoRowsQuery()


def _db() -> _RecordingDb:
    return _RecordingDb()


def _sdb(db: _RecordingDb) -> Session:
    return cast(Session, db)


class _FakeManager:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def read_file(self, _sandbox_id, _session_id, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def list_directory(self, _sandbox_id, _session_id, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        if any(key.startswith(prefix) or key == path for key in self.files):
            return ["ok"]
        raise FileNotFoundError(path)

    def write_files_to_sandbox(self, **_kwargs) -> None:
        return None


_LANE_IDS: Final[tuple[tuple[str, str], ...]] = (
    ("extract", "extract"),
    ("compose", "compose"),
)
_LANES_PLAN: dict[str, Any] = {
    "goal": "Financial report analysis",
    "lanes": [
        {
            "id": lane_id,
            "role": role,
            "done_when": [f"outputs/{lane_id}/{lane_id}.md"],
        }
        for lane_id, role in _LANE_IDS
    ],
}


def _lane_job() -> CraftJob:
    plan = parse_plan(_LANES_PLAN)
    graph = compile_graph("tax", plan)
    job = _job("tax")
    job.status = CraftJobStatus.WAITING_LANES
    state = load_state(job)
    state.graph = graph.to_snapshot()
    persist_state(job, state)
    job.specialists = [
        SimpleNamespace(
            status=CraftJobSpecialistStatus.RUNNING,
            node_id=f"lane:{lane_id}",
            session_id=uuid4(),
            role=role,
            output_artifact_ids=[],
            finished_at=None,
            error_detail=None,
        )
        for lane_id, role in _LANE_IDS
    ]
    return job


def _patch_runtime(monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]) -> None:
    manager = _FakeManager(files)
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=manager: _fake)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._sandbox_id_for_session",
        lambda *_a, **_k: uuid4(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.scan_artifacts", lambda **_k: {}
    )


def test_job_turn_budgets_clamped_between_caps() -> None:
    for phase_budget, expected in (
        (900, INTERACTIVE_TURN_HARD_CAP_SECONDS),
        (INTERACTIVE_TURN_HARD_CAP_SECONDS, INTERACTIVE_TURN_HARD_CAP_SECONDS),
        (45 * 60, 45 * 60),
        (7200, SCHEDULED_RUN_HARD_CAP_SECONDS),
    ):
        job = SimpleNamespace(phase_budget_seconds=phase_budget)
        budgets = job_turn_budgets(cast(CraftJob, job))
        assert budgets is not None
        soft, hard = budgets
        assert hard == expected, (phase_budget, hard)
        assert soft < hard
    assert job_turn_budgets(None) is None


def test_is_transient_turn_error_classification() -> None:
    transient = [
        '{"message":"The upstream LLM request failed.","type":"upstream_error"}',
        "The selected model is temporarily rate limited.",
        "hard time cap exceeded (2700s)",
        "Turn ended before opencode returned a final response.",
        "rate_limit_error: too many requests",
    ]
    for detail in transient:
        assert is_transient_turn_error(detail), detail
    not_transient = [
        None,
        "",
        "Job lease lost mid-turn.",
        "Another turn was still running",
    ]
    for detail in not_transient:
        assert not is_transient_turn_error(detail), detail


def test_skill_binding_preamble() -> None:
    preamble = _skill_binding_preamble(["financial-report-analysis"], "写财报分析报告")
    assert "financial-report-analysis" in preamble
    assert preamble.endswith("\n\n")
    # Briefs already state the requirement; never double it.
    brief = "The user explicitly requires the skill(s) `x`.\nGoal"
    assert _skill_binding_preamble(["x"], brief) == ""
    assert _skill_binding_preamble(None, "plain") == ""
    assert _skill_binding_preamble([], "plain") == ""


def test_brief_binds_required_skills_on_plan_and_lanes() -> None:
    plan = parse_plan(_LANES_PLAN)
    graph = compile_graph("tax", plan)
    state = load_state(_lane_job())
    state.selected_skill_ids = ["financial-report-analysis"]

    plan_node = graph.get("plan")
    assert plan_node is not None
    plan_brief = assemble_brief(node=plan_node, state=state, job_name="j", domain="tax")
    assert "user explicitly requires the skill(s) `financial-report-analysis`" in (
        plan_brief
    )
    assert "backbone" in plan_brief

    lane_node = graph.get("lane:compose")
    assert lane_node is not None
    lane_brief = assemble_brief(node=lane_node, state=state, job_name="j", domain="tax")
    assert "user requires skill(s) `financial-report-analysis`" in lane_brief

    unselected = empty_state()
    assert "explicitly requires" not in assemble_brief(
        node=plan_node, state=unselected, job_name="j", domain="tax"
    )


def test_successful_lane_not_poisoned_by_failed_sibling(monkeypatch) -> None:
    job = _lane_job()
    extract, compose = job.specialists
    # extract already failed; compose's turn succeeded with its deliverable
    # (the continuation marks specialists before after_lane_turn runs).
    extract.status = CraftJobSpecialistStatus.FAILED
    extract.error_detail = "hard time cap exceeded (1800s)"
    compose.status = CraftJobSpecialistStatus.SUCCEEDED
    _patch_runtime(monkeypatch, {"outputs/compose/compose.md": b"# report\n"})
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _StubSessionManager,
    )

    after_lane_turn(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:compose",
    )

    assert compose.status == CraftJobSpecialistStatus.SUCCEEDED
    assert "lane:compose" in load_state(job).completed_nodes
    assert job.status == CraftJobStatus.FAILED
    assert "A specialist session failed" in (job.error_detail or "")
    assert "lane:extract" in (job.error_detail or "")


def test_transient_lane_failure_retries_instead_of_failing(
    monkeypatch,
) -> None:
    job = _lane_job()
    enqueued: list[str] = []
    _patch_runtime(monkeypatch, {})
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: enqueued.append(str(kwargs.get("prompt") or "")),
    )

    after_lane_turn(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        specialist_ok=False,
        node_id="lane:extract",
        turn_error_detail="hard time cap exceeded (2700s)",
    )

    assert enqueued, "a transient lane failure must re-drive the lane"
    assert job.status == CraftJobStatus.WAITING_LANES
    assert job.specialists[0].status == CraftJobSpecialistStatus.RUNNING
    assert "outputs/extract/extract.md" in enqueued[0]
    assert "hard time cap exceeded" in enqueued[0]


def test_lane_failure_retry_limit_fails_job(monkeypatch) -> None:
    job = _lane_job()
    state = load_state(job)
    state.node_attempts = {"lane:extract": 2}
    persist_state(job, state)
    enqueued: list[str] = []
    _patch_runtime(monkeypatch, {})
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: enqueued.append(str(kwargs.get("prompt") or "")),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _StubSessionManager,
    )

    after_lane_turn(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        specialist_ok=False,
        node_id="lane:extract",
        turn_error_detail="hard time cap exceeded (2700s)",
    )

    assert not enqueued, "third attempt is terminal"
    assert job.status == CraftJobStatus.FAILED


def test_nontransient_lane_failure_fails_without_retry(monkeypatch) -> None:
    job = _lane_job()
    # The continuation marks the specialist FAILED before after_lane_turn.
    job.specialists[0].status = CraftJobSpecialistStatus.FAILED
    job.specialists[0].error_detail = "Cancelled"
    enqueued: list[str] = []
    _patch_runtime(monkeypatch, {})
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: enqueued.append(str(kwargs.get("prompt") or "")),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _StubSessionManager,
    )

    after_lane_turn(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        specialist_ok=False,
        node_id="lane:extract",
        turn_error_detail=None,
    )

    assert not enqueued
    assert job.specialists[0].status == CraftJobSpecialistStatus.FAILED
    # Sibling still running: the job waits, it does not fail early.
    assert job.status == CraftJobStatus.WAITING_LANES


def test_lease_lost_lane_settles_but_does_not_advance(monkeypatch) -> None:
    job = _lane_job()
    job.lease_owner = "winner"
    # Deliverable present so the contract gate passes; the continuation marks
    # the specialist SUCCEEDED before after_lane_turn runs. The sibling is
    # also terminal so ONLY the lease gates the advance.
    job.specialists[0].status = CraftJobSpecialistStatus.SUCCEEDED
    job.specialists[1].status = CraftJobSpecialistStatus.SUCCEEDED
    state = load_state(job)
    state.completed_nodes = ["lane:compose"]
    persist_state(job, state)
    _patch_runtime(monkeypatch, {"outputs/extract/extract.md": b"notes\n"})
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: enqueued.append(str(kwargs.get("prompt") or "")),
    )
    db = _db()

    after_lane_turn(
        _sdb(db),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:extract",
        lease_owner="loser",
    )

    # Settlement is per-lane fact: card and completed_nodes land even though
    # the lease was lost; only the superstep advance is skipped.
    assert "lane:extract" in load_state(job).completed_nodes
    cards = [
        row
        for row in db.added
        if isinstance(row, BuildMessage)
        and isinstance(row.message_metadata, dict)
        and row.message_metadata.get("lane_task_node_id") == "lane:extract"
    ]
    assert cards, "lease-lost lane must still settle its card"
    stream = cards[0].message_metadata.get("streamItems") or []
    assert stream and stream[0]["toolCall"]["status"] == "completed"
    assert not enqueued, "a lease-losing turn must not advance the job"


def test_concurrent_heartbeats_do_not_drop_lane_completion(monkeypatch) -> None:
    """The 11d59cb2 incident: sibling lane heartbeats flipped job.lease_owner,
    so a finishing lane's settlement was skipped and the kernel re-spawned it.
    Settlement must not depend on owning the job lease."""
    job = _lane_job()
    # extract's turn finished while the sibling's heartbeat owned the lease.
    job.lease_owner = "sibling-heartbeat"
    job.specialists[0].status = CraftJobSpecialistStatus.SUCCEEDED
    _patch_runtime(monkeypatch, {"outputs/extract/extract.md": b"notes\n"})

    after_lane_turn(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:extract",
        lease_owner="extract-turn",
    )

    assert "lane:extract" in load_state(job).completed_nodes
    assert job.specialists[0].status == CraftJobSpecialistStatus.SUCCEEDED


def test_finalize_job_failure_settles_open_lanes_and_persists_error_row(
    monkeypatch,
) -> None:
    job = _lane_job()
    interrupted: list[object] = []

    class _Manager(_StubSessionManager):
        def interrupt_message(self, *args: object, **_kwargs: object) -> bool:
            if args:
                interrupted.append(args[0])
            return True

    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _Manager,
    )
    db = _db()

    finalize_job_failure(
        _sdb(db), job=job, user_id=uuid4(), error_detail="A specialist session failed"
    )

    assert job.status == CraftJobStatus.FAILED
    for specialist in job.specialists:
        assert specialist.status == CraftJobSpecialistStatus.FAILED
        assert specialist.error_detail == "Job failed"
    error_rows = [
        row
        for row in db.added
        if isinstance(row, BuildMessage)
        and isinstance(row.message_metadata, dict)
        and row.message_metadata.get("type") == "error"
    ]
    assert error_rows, "the parent transcript must explain the failure"
    message = error_rows[0].message_metadata["message"]
    assert "A specialist session failed" in message
    assert interrupted, "running lane turns must get the interrupt fence"


def _second_round_specialist(job: CraftJob, session_id: UUID) -> None:
    from onyx.db.models import CraftJobSpecialist as _Specialist

    job.specialists.append(
        cast(
            _Specialist,
            SimpleNamespace(
                status=CraftJobSpecialistStatus.SUCCEEDED,
                node_id="lane:extract",
                session_id=session_id,
                role="extract",
                output_artifact_ids=[],
                finished_at=None,
                error_detail=None,
            ),
        )
    )


def test_specialist_for_settlement_matches_session_not_oldest() -> None:
    from onyx.server.features.build.jobs.kernel import _specialist_for_settlement

    job = _lane_job()
    new_session = uuid4()
    _second_round_specialist(job, new_session)
    matched = _specialist_for_settlement(job, "lane:extract", new_session)
    assert matched is job.specialists[-1]
    fallback = _specialist_for_settlement(job, "lane:extract", None)
    assert fallback is job.specialists[-1], "fallback picks the newest row"


def test_multi_round_lane_settlement_keeps_one_card(monkeypatch) -> None:
    """Ghost-cancel repro: round-2 settlement used to carry round-1's session
    id, so the card upsert saw a different specialist and cancelled the fresh
    card. The settlement card must carry the settling round's session."""
    from onyx.server.features.build.jobs.lane_task import lane_task_upsert_action

    job = _lane_job()
    job.specialists[0].status = CraftJobSpecialistStatus.SUCCEEDED
    new_session = uuid4()
    _second_round_specialist(job, new_session)
    _patch_runtime(monkeypatch, {"outputs/extract/extract.md": b"notes\n"})
    db = _db()

    after_lane_turn(
        _sdb(db),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:extract",
        specialist_session_id=new_session,
    )

    cards = [
        row
        for row in db.added
        if isinstance(row, BuildMessage)
        and isinstance(row.message_metadata, dict)
        and row.message_metadata.get("lane_task_node_id") == "lane:extract"
    ]
    assert cards
    tool = (cards[0].message_metadata["streamItems"] or [{}])[0]["toolCall"]
    assert tool["subagentSessionId"] == str(new_session)
    # With matching sessions the upsert updates in place instead of splitting
    # the card into a cancelled one plus a new completed one.
    from onyx.server.features.build.jobs.lane_task import lane_task_card_metadata

    existing = lane_task_card_metadata(
        node_id="lane:extract",
        name="extract",
        status="in_progress",
        notes_path="outputs/extract/extract.md",
        specialist_session_id=new_session,
        role="extract",
    )
    assert lane_task_upsert_action(existing, cards[0].message_metadata) == "update"


def test_spawn_lanes_heals_succeeded_lane_without_respawn(monkeypatch) -> None:
    from onyx.server.features.build.jobs.kernel import _spawn_lanes, load_graph

    job = _lane_job()
    job.status = CraftJobStatus.RUNNING
    job.specialists[0].status = CraftJobSpecialistStatus.SUCCEEDED
    job.specialists[1].status = CraftJobSpecialistStatus.SUCCEEDED
    state = load_state(job)
    # Completion writes were lost: neither lane is in completed_nodes.
    graph = load_graph(job, state)
    _patch_runtime(
        monkeypatch,
        {"outputs/extract/extract.md": b"n\n", "outputs/compose/compose.md": b"n\n"},
    )
    dispatched: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._dispatch_next",
        lambda *_a, **_k: dispatched.append("dispatch"),
    )
    created: list[str] = []

    class _NoSpawnManager(_StubSessionManager):
        def create_session(self, *_args: object, **_kwargs: object) -> object:
            created.append("spawn")
            return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _NoSpawnManager,
    )

    extract_node = graph.get("lane:extract")
    assert extract_node is not None
    _spawn_lanes(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        state=state,
        lanes=[extract_node],
    )

    assert not created, "a succeeded lane with deliverables must not re-run"
    assert "lane:extract" in load_state(job).completed_nodes
    assert dispatched, "all-healed ready lanes must advance the job"


def test_spawn_lanes_respawn_counts_attempts_and_caps(monkeypatch) -> None:
    from onyx.server.features.build.jobs.kernel import _spawn_lanes, load_graph

    job = _lane_job()
    job.status = CraftJobStatus.RUNNING
    job.specialists[0].status = CraftJobSpecialistStatus.FAILED  # no heal
    state = load_state(job)
    graph = load_graph(job, state)
    state.node_attempts = {"lane:extract": 2}
    persist_state(job, state)
    _patch_runtime(monkeypatch, {})
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager",
        _StubSessionManager,
    )

    extract_node = graph.get("lane:extract")
    assert extract_node is not None
    _spawn_lanes(
        _sdb(_db()),
        job=job,
        user_id=uuid4(),
        state=state,
        lanes=[extract_node],
    )

    assert job.status == CraftJobStatus.FAILED, "third respawn attempt is terminal"
