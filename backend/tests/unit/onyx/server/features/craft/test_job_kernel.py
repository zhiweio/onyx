"""Kernel superstep: no silent advance, review revise, lane join."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import CraftJob
from onyx.server.features.build.jobs.channels import empty_state
from onyx.server.features.build.jobs.gates import ContractGateResult, GateMissing
from onyx.server.features.build.jobs.graph import compile_graph
from onyx.server.features.build.jobs.kernel import (
    after_lane_turn,
    after_worker_turn,
    initialize_job_state,
    load_state,
    maybe_revise_after_review,
    persist_state,
)


def _job(domain: str = "tax", **kwargs):
    graph = compile_graph(domain)
    values = {
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


def _db() -> Session:
    return cast(
        Session, SimpleNamespace(commit=lambda: None, add=lambda *_a, **_k: None)
    )


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


def test_missing_plan_does_not_advance(monkeypatch) -> None:
    job = _job()
    enqueued: list[str] = []
    empty = _FakeManager({})
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=empty: _fake)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    db = _db()
    after_worker_turn(
        db,
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    state = load_state(job)
    assert "plan" not in state.completed_nodes
    assert job.status == CraftJobStatus.RUNNING
    assert enqueued
    assert "not done" in enqueued[0]


def test_review_gap_reopens_owner(monkeypatch) -> None:
    from onyx.server.features.build.jobs.plan import parse_plan

    plan = parse_plan(
        {
            "goal": "x",
            "phases": [
                {"id": "plan", "kind": "plan"},
                {"id": "compose", "kind": "compose"},
                {"id": "review", "kind": "review"},
            ],
        }
    )
    graph = compile_graph("", plan)
    job = _job()
    state = load_state(job)
    state.completed_nodes = ["plan", "compose"]
    state.graph = graph.to_snapshot()
    persist_state(job, state)
    review = graph.get("review")
    assert review is not None
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **_k: uuid4(),
    )
    db = _db()
    gate = ContractGateResult(
        passed=False,
        missing=[
            GateMissing(
                path="outputs/markdown/report.md",
                reason="missing table",
                owner_node="compose",
            )
        ],
    )
    revised = maybe_revise_after_review(
        db,
        job=job,
        user_id=uuid4(),
        state=state,
        node=review,
        gate=gate,
    )
    assert revised is True
    next_state = load_state(job)
    assert "compose" not in next_state.completed_nodes
    assert next_state.last_node == "compose"


def test_review_self_owner_does_not_reenqueue_qa(monkeypatch) -> None:
    from onyx.server.features.build.jobs.phase_gate import DEFAULT_PHASE_RETRY_LIMIT
    from onyx.server.features.build.jobs.plan import parse_plan

    plan = parse_plan(
        {
            "goal": "x",
            "phases": [
                {"id": "plan", "kind": "plan"},
                {"id": "compose", "kind": "compose"},
                {"id": "qa", "kind": "review"},
            ],
        }
    )
    graph = compile_graph("", plan)
    job = _job()
    state = load_state(job)
    state.completed_nodes = ["plan", "compose"]
    state.last_node = "qa"
    state.cursor = ["qa"]
    state.graph = graph.to_snapshot()
    persist_state(job, state)
    qa = graph.get("qa")
    assert qa is not None
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(str(kwargs["phase"]["id"])) or uuid4(),
    )
    db = _db()
    gate = ContractGateResult(
        passed=False,
        missing=[
            GateMissing(
                path="outputs/review/REVIEW.json",
                reason="REVIEW.json needs passed",
                owner_node="qa",
            )
        ],
    )
    revised = maybe_revise_after_review(
        db,
        job=job,
        user_id=uuid4(),
        state=state,
        node=qa,
        gate=gate,
    )
    assert revised is False
    next_state = load_state(job)
    assert "compose" in next_state.completed_nodes
    assert enqueued == []

    empty = _FakeManager({})
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=empty: _fake)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.stop_gate",
        lambda **_k: gate,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.scan_artifacts",
        lambda **_k: {},
    )
    user_id = uuid4()
    sandbox_id = uuid4()
    for _ in range(DEFAULT_PHASE_RETRY_LIMIT + 2):
        if job.status != CraftJobStatus.RUNNING:
            break
        after_worker_turn(
            db,
            job=job,
            user_id=user_id,
            sandbox_id=sandbox_id,
            session_id=job.session_id,
            deadline_exceeded=False,
        )
    assert job.status == CraftJobStatus.FAILED
    assert enqueued.count("qa") < DEFAULT_PHASE_RETRY_LIMIT + 2


def test_mark_job_cancelled_stops_open_specialists() -> None:
    from onyx.db.craft_job import mark_job_cancelled

    running = SimpleNamespace(
        status=CraftJobSpecialistStatus.RUNNING,
        error_detail=None,
        finished_at=None,
        output_artifact_ids=None,
    )
    succeeded = SimpleNamespace(
        status=CraftJobSpecialistStatus.SUCCEEDED,
        error_detail=None,
        finished_at="done",
        output_artifact_ids=None,
    )
    pending = SimpleNamespace(
        status=CraftJobSpecialistStatus.PENDING,
        error_detail=None,
        finished_at=None,
        output_artifact_ids=None,
    )
    job = _job("biomed")
    job.status = CraftJobStatus.WAITING_LANES
    job.specialists = [running, succeeded, pending]
    mark_job_cancelled(job)
    assert job.status == CraftJobStatus.CANCELLED
    assert running.status == CraftJobSpecialistStatus.FAILED
    assert running.error_detail == "Cancelled"
    assert succeeded.status == CraftJobSpecialistStatus.SUCCEEDED
    assert pending.status == CraftJobSpecialistStatus.FAILED
    assert pending.error_detail == "Cancelled"


def test_mark_job_cancelled_stops_leftover_lanes_after_prior_cancel() -> None:
    from onyx.db.craft_job import mark_job_cancelled

    leftover = SimpleNamespace(
        status=CraftJobSpecialistStatus.RUNNING,
        error_detail=None,
        finished_at=None,
        output_artifact_ids=None,
    )
    job = _job("biomed")
    job.status = CraftJobStatus.CANCELLED
    job.specialists = [leftover]
    mark_job_cancelled(job)
    assert job.status == CraftJobStatus.CANCELLED
    assert leftover.status == CraftJobSpecialistStatus.FAILED
    assert leftover.error_detail == "Cancelled"


def test_cancelled_job_does_not_resume_after_lane_turn() -> None:
    job = _job("biomed")
    job.status = CraftJobStatus.CANCELLED
    job.specialists = [
        SimpleNamespace(
            status=CraftJobSpecialistStatus.SUCCEEDED,
            node_id="lane:literature",
            session_id=uuid4(),
            role="literature",
        ),
        SimpleNamespace(
            status=CraftJobSpecialistStatus.FAILED,
            node_id="lane:clinical",
            session_id=uuid4(),
            role="clinical",
        ),
    ]
    after_lane_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        specialist_ok=False,
        node_id="lane:clinical",
    )
    assert job.status == CraftJobStatus.CANCELLED


def test_cancelled_job_does_not_advance_after_worker_turn(monkeypatch) -> None:
    job = _job()
    job.status = CraftJobStatus.CANCELLED
    called = {"scan": 0}

    def _scan(**_kwargs):
        called["scan"] += 1
        return {}

    monkeypatch.setattr("onyx.server.features.build.jobs.kernel.scan_artifacts", _scan)
    after_worker_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert job.status == CraftJobStatus.CANCELLED
    assert called["scan"] == 0


def test_lane_join_waits_until_all_terminal() -> None:
    job = _job("biomed")
    job.status = CraftJobStatus.WAITING_LANES
    job.specialists = [
        SimpleNamespace(
            status=CraftJobSpecialistStatus.SUCCEEDED,
            node_id="lane:literature",
            session_id=uuid4(),
            role="literature",
        ),
        SimpleNamespace(
            status=CraftJobSpecialistStatus.RUNNING,
            node_id="lane:clinical",
            session_id=uuid4(),
            role="clinical",
        ),
    ]
    db = _db()
    after_lane_turn(
        db,
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:literature",
    )
    assert job.status == CraftJobStatus.WAITING_LANES


def test_empty_state_has_no_cursor_progress() -> None:
    state = empty_state()
    assert state.completed_nodes == []
    assert state.cursor == []


def test_lease_expired_from_checkpoint() -> None:
    from datetime import datetime, timedelta, timezone

    from onyx.server.features.build.jobs.kernel import lease_expired, renew_lease

    job = _job()
    renew_lease(job, owner="turn-1", seconds=1)
    assert job.lease_owner == "turn-1"
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert lease_expired(job) is True


def test_lease_expired_redispaches_same_node(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    job = _job()
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    enqueued: list[str] = []
    empty = _FakeManager({})
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=empty: _fake)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    db = _db()
    after_worker_turn(
        db,
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    state = load_state(job)
    assert "plan" not in state.completed_nodes
    assert state.drain_reason == "lease_expired"
    assert job.drain_reason == "lease_expired"
    assert enqueued
    assert "not done" in enqueued[0]


def test_replay_deltas_rebuilds_from_rows(monkeypatch) -> None:
    from onyx.server.features.build.jobs.checkpoint import replay_deltas

    rows = [
        SimpleNamespace(writes={"goal": "g", "cursor": ["plan"]}),
        SimpleNamespace(writes={"completed_nodes": ["plan"]}),
    ]
    monkeypatch.setattr(
        "onyx.db.craft_job.list_job_checkpoints",
        lambda *_a, **_k: rows,
    )
    state = replay_deltas(cast(Session, SimpleNamespace()), job_id=uuid4())
    assert state.goal == "g"
    assert "plan" in state.completed_nodes


def test_work_node_retries_until_done_json(monkeypatch) -> None:
    from onyx.server.features.build.jobs.plan import parse_plan

    plan = parse_plan({"goal": "Ship the dashboard"})
    graph = compile_graph("", plan)
    job = _job()
    state = load_state(job)
    state.completed_nodes = ["plan"]
    state.last_node = "work"
    state.cursor = ["work"]
    state.graph = graph.to_snapshot()
    persist_state(job, state)

    files: dict[str, bytes] = {
        "outputs/TODO.md": b"- [ ] implement the page\n",
    }
    manager = _FakeManager(files)
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=manager: _fake)
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    db = _db()
    after_worker_turn(
        db,
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert "work" not in load_state(job).completed_nodes
    assert job.status == CraftJobStatus.RUNNING
    assert enqueued

    files["outputs/TODO.md"] = b"- [x] implement the page\n"
    files["outputs/DONE.json"] = b'{"done": true, "summary": "dashboard shipped"}\n'
    after_worker_turn(
        db,
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert "work" in load_state(job).completed_nodes
    assert job.status == CraftJobStatus.SUCCEEDED


def test_mid_job_work_node_allows_later_open_todos(monkeypatch) -> None:
    from onyx.server.features.build.jobs.plan import parse_plan

    plan = parse_plan(
        {
            "goal": "Ship the dashboard",
            "phases": [
                {
                    "id": "scope",
                    "kind": "work",
                    "done_when": ["outputs/tmp/scoping.md"],
                },
                {
                    "id": "build",
                    "kind": "work",
                    "done_when": ["outputs/DONE.json"],
                },
            ],
        }
    )
    graph = compile_graph("", plan)
    job = _job()
    state = load_state(job)
    state.completed_nodes = ["plan"]
    state.last_node = "scope"
    state.cursor = ["scope"]
    state.graph = graph.to_snapshot()
    persist_state(job, state)

    files: dict[str, bytes] = {
        "outputs/tmp/scoping.md": b"# Scope\nReady.\n",
        "outputs/TODO.md": b"- [x] scope\n- [ ] build later\n",
    }
    manager = _FakeManager(files)
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=manager: _fake)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **_k: uuid4(),
    )
    after_worker_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert "scope" in load_state(job).completed_nodes


def test_assemble_brief_hides_protocol() -> None:
    from onyx.server.features.build.jobs.assembler import assemble_brief

    graph = compile_graph("tax")
    node = graph.get("plan")
    assert node is not None
    brief = assemble_brief(
        node=node,
        state=empty_state(),
        job_name="job",
        domain="tax",
        user_prompt="goal",
    )
    assert "long-job-protocol" not in brief
    assert "PHASE_DONE" not in brief or "Do not write PHASE_DONE" in brief
    assert "Current node: plan" in brief
    assert "Do not assume a report" in brief
    assert "User-visible reply" in brief
    assert "lanes [{role" in brief
    assert "ask_delivery boolean" in brief


def test_continue_persists_empty_visible_text(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_message(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.create_message",
        fake_create_message,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_cache_backend",
        lambda: object(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.acquire_active_turn_lock",
        lambda *_a, **_k: SimpleNamespace(release=lambda: None),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.count_user_messages",
        lambda *_a, **_k: 1,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.create_interactive_turn",
        lambda **_k: SimpleNamespace(turn_id=uuid4()),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.start_interactive_turn_runner",
        lambda *_a, **_k: None,
    )
    from onyx.server.features.build.jobs.continuation import _enqueue_phase_turn

    _enqueue_phase_turn(
        _db(),
        session_id=uuid4(),
        user_id=uuid4(),
        prompt="HOST BRIEF MUST STAY OFF TRANSCRIPT",
    )
    metadata = captured["message_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["content"]["text"] == ""
    assert metadata["craft_job_continue"] is True
    assert "HOST BRIEF" not in str(metadata)

    _enqueue_phase_turn(
        _db(),
        session_id=uuid4(),
        user_id=uuid4(),
        prompt="HOST BRIEF MUST STAY OFF TRANSCRIPT",
        visible_user_text="Write the GLP-1 report",
    )
    metadata = captured["message_metadata"]
    assert isinstance(metadata, dict)
    assert metadata["content"]["text"] == "Write the GLP-1 report"
    assert metadata["craft_job_continue"] is False


def test_enqueue_stamps_job_picker_selection(monkeypatch) -> None:
    captured: dict[str, object] = {}
    job = _job()
    state = load_state(job)
    state.selected_skill_ids = ["hithink-finance"]
    state.selected_mcp_server_ids = [7, 9]
    persist_state(job, state)

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.create_message",
        lambda **_k: SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_cache_backend",
        lambda: object(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.acquire_active_turn_lock",
        lambda *_a, **_k: SimpleNamespace(release=lambda: None),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.count_user_messages",
        lambda *_a, **_k: 1,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_open_job_for_session",
        lambda *_a, **_k: job,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.get_specialist_for_session",
        lambda *_a, **_k: None,
    )

    def fake_create_turn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(turn_id=uuid4())

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.create_interactive_turn",
        fake_create_turn,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.start_interactive_turn_runner",
        lambda *_a, **_k: None,
    )
    from onyx.server.features.build.jobs.continuation import _enqueue_phase_turn

    _enqueue_phase_turn(
        _db(),
        session_id=job.session_id,
        user_id=uuid4(),
        prompt="HOST BRIEF",
    )
    assert captured["selected_skill_ids"] == ["hithink-finance"]
    assert captured["selected_mcp_server_ids"] == [7, 9]


def test_lane_turn_completes_despite_parent_host_files(monkeypatch) -> None:
    from onyx.server.features.build.jobs.channels import ArtifactRecord
    from onyx.server.features.build.jobs.plan import parse_plan

    notes = "outputs/normalized/epi-patient-pool.md"
    plan = parse_plan(
        {
            "goal": "Clinical initiation",
            "lanes": [
                {
                    "id": "researcher",
                    "role": "researcher",
                    "done_when": [notes],
                },
                {
                    "id": "researcher-2",
                    "role": "researcher",
                    "done_when": ["outputs/normalized/pipeline.csv"],
                },
            ],
        }
    )
    graph = compile_graph("biomed", plan)
    job = _job("biomed")
    job.status = CraftJobStatus.WAITING_LANES
    state = load_state(job)
    state.graph = graph.to_snapshot()
    persist_state(job, state)
    researcher = SimpleNamespace(
        status=CraftJobSpecialistStatus.SUCCEEDED,
        node_id="lane:researcher",
        session_id=uuid4(),
        role="researcher",
        output_artifact_ids=[],
        finished_at=None,
    )
    other = SimpleNamespace(
        status=CraftJobSpecialistStatus.RUNNING,
        node_id="lane:researcher-2",
        session_id=uuid4(),
        role="researcher",
        output_artifact_ids=[],
        finished_at=None,
    )
    job.specialists = [researcher, other]
    files = {
        notes: b"China NHL 80829/year. https://example.com [1]\n",
        "outputs/DONE.json": b'{"done": true}\n',
        "outputs/markdown/epi-patient-pool.md": b"# copy\n",
    }
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
        "onyx.server.features.build.jobs.kernel.scan_artifacts",
        lambda **_k: {
            notes: ArtifactRecord(
                path=notes,
                producer_node="lane:researcher",
                nonempty=True,
                summary="notes",
            )
        },
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: enqueued.append(str(kwargs.get("prompt") or "")),
    )
    after_lane_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:researcher",
    )
    assert enqueued == []
    assert researcher.status == CraftJobSpecialistStatus.SUCCEEDED
    assert "lane:researcher" in load_state(job).completed_nodes
    assert job.status == CraftJobStatus.WAITING_LANES


def test_lane_sets_output_artifact_ids_on_shared_outputs(monkeypatch) -> None:
    from onyx.server.features.build.jobs.channels import ArtifactRecord
    from onyx.server.features.build.jobs.plan import parse_plan

    plan = parse_plan(
        {
            "goal": "GLP-1",
            "lanes": [{"role": "literature"}, {"role": "clinical"}],
        }
    )
    graph = compile_graph("biomed", plan)
    job = _job("biomed")
    job.status = CraftJobStatus.WAITING_LANES
    state = load_state(job)
    state.graph = graph.to_snapshot()
    persist_state(job, state)

    notes = "outputs/lanes/literature/NOTES.md"
    files = {notes: b"See https://example.com [1]\n"}
    literature = SimpleNamespace(
        status=CraftJobSpecialistStatus.SUCCEEDED,
        node_id="lane:literature",
        session_id=uuid4(),
        role="literature",
        output_artifact_ids=[],
        finished_at=None,
    )
    clinical = SimpleNamespace(
        status=CraftJobSpecialistStatus.RUNNING,
        node_id="lane:clinical",
        session_id=uuid4(),
        role="clinical",
        output_artifact_ids=[],
        finished_at=None,
    )
    job.specialists = [literature, clinical]
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
        "onyx.server.features.build.jobs.kernel.scan_artifacts",
        lambda **_k: {
            notes: ArtifactRecord(
                path=notes,
                producer_node="lane:literature",
                nonempty=True,
                summary="notes",
            )
        },
    )
    after_lane_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:literature",
    )
    assert literature.output_artifact_ids == [notes]
    assert job.status == CraftJobStatus.WAITING_LANES


def test_lane_search_gate_keeps_interrupt_on_job_state(monkeypatch) -> None:
    from onyx.server.features.build.jobs.plan import parse_plan

    notes = "outputs/research/literature/notes.md"
    plan = parse_plan(
        {
            "goal": "Use Parallel Search MCP",
            "lanes": [
                {
                    "id": "literature",
                    "role": "biomed-literature",
                    "done_when": [notes],
                }
            ],
        }
    )
    graph = compile_graph("biomed", plan)
    job = _job("biomed")
    job.status = CraftJobStatus.WAITING_LANES
    state = load_state(job)
    state.goal = "对本任务的公开网络检索，使用 Parallel Search MCP"
    state.graph = graph.to_snapshot()
    persist_state(job, state)
    literature = SimpleNamespace(
        status=CraftJobSpecialistStatus.SUCCEEDED,
        node_id="lane:biomed-literature",
        session_id=uuid4(),
        role="literature",
        output_artifact_ids=[],
        finished_at=None,
    )
    job.specialists = [literature]
    manager = _FakeManager({notes: b"# notes\nno sources retrieved\n"})
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
    after_lane_turn(
        _db(),
        job=job,
        user_id=uuid4(),
        specialist_ok=True,
        node_id="lane:biomed-literature",
    )
    stored = load_state(job)
    assert job.status == CraftJobStatus.INTERRUPTED
    assert stored.interrupt is not None
    assert stored.interrupt.kind == "clarify"
    assert "Search is not available" in stored.interrupt.payload.get("summary", "")
    assert stored.interrupt.payload.get("node_id") == "lane:biomed-literature"


def test_named_search_mcp_unavailable_interrupts(monkeypatch) -> None:
    from onyx.server.features.build.jobs.kernel import (
        _interrupt_if_named_mcp_unavailable,
    )

    job = _job()
    state = load_state(job)
    state.goal = "Use Parallel Search MCP for GLP-1 citations"
    persist_state(job, state)
    monkeypatch.setattr(
        "onyx.db.users.fetch_user_by_id",
        lambda *_a, **_k: SimpleNamespace(id=uuid4()),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.sandbox.util.mcp_config.craft_mcp_tool_surface",
        lambda *_a, **_k: [],
    )
    interrupted = _interrupt_if_named_mcp_unavailable(
        _db(), job=job, user_id=uuid4(), state=state
    )
    assert interrupted is True
    assert job.status == CraftJobStatus.INTERRUPTED
    assert job.status != CraftJobStatus.SUCCEEDED


def test_reap_inactive_lanes_finishes_stale_specialist(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone

    from onyx.server.features.build.jobs.kernel import reap_inactive_lanes

    job = _job()
    job.status = CraftJobStatus.WAITING_LANES
    job.phase_budget_seconds = 60
    stale = SimpleNamespace(
        status=CraftJobSpecialistStatus.RUNNING,
        node_id="lane:literature",
        session_id=uuid4(),
        role="literature",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        finished_at=None,
        output_artifact_ids=[],
        error_detail=None,
    )
    job.specialists = [stale]
    finished: list[str] = []

    def _mark(specialist, *, status, error_detail=None, output_artifact_ids=None):
        specialist.status = status
        specialist.error_detail = error_detail
        specialist.finished_at = datetime.now(timezone.utc)
        finished.append(error_detail or "")

    monkeypatch.setattr(
        "onyx.db.craft_job.mark_specialist_finished",
        _mark,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.after_lane_turn",
        lambda *_a, **_k: None,
    )
    reaped = reap_inactive_lanes(_db(), job=job, user_id=uuid4())
    assert reaped is True
    assert stale.status == CraftJobSpecialistStatus.FAILED
    assert finished == ["Lane inactive"]
