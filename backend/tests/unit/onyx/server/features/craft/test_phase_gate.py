"""Phase gate and continuation golden path (no silent advance)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from onyx.db.enums import CraftJobStatus
from onyx.server.features.build.jobs import continuation as continuation_mod
from onyx.server.features.build.jobs.phase_gate import (
    DEFAULT_PHASE_RETRY_LIMIT,
    evaluate_phase_gate,
    increment_gate_retries,
    retry_prompt,
)
from onyx.server.features.build.jobs.plan import PLAN_JSON_PATH
from onyx.server.features.build.jobs.protocol import (
    PHASE_DONE_PATH,
    default_phases_for_domain,
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


def _job(**kwargs):
    phases = default_phases_for_domain("tax")
    phases[0]["status"] = "running"
    values = {
        "id": uuid4(),
        "session_id": uuid4(),
        "domain": "tax",
        "name": "golden",
        "status": CraftJobStatus.RUNNING,
        "phases": phases,
        "current_phase_index": 0,
        "started_at": None,
        "total_budget_seconds": 7200,
        "phase_budget_seconds": 1500,
        "error_detail": None,
        "specialists": [],
        "state": {},
        "project_id": uuid4(),
        "scenario_id": None,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_gate_pass_when_phase_done_and_files_exist(monkeypatch) -> None:
    files = {
        PHASE_DONE_PATH: b"plan\n",
        PLAN_JSON_PATH: b'{"goal":"g","phases":[{"id":"plan","kind":"plan"}]}',
    }
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        lambda: _FakeManager(files),
    )
    result = evaluate_phase_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        phase={"id": "plan", "done_when": [PLAN_JSON_PATH, PHASE_DONE_PATH]},
        deadline_exceeded=False,
    )
    assert result.passed is True
    assert result.missing == []


def test_gate_missing_file_does_not_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        lambda: _FakeManager({PHASE_DONE_PATH: b"plan\n"}),
    )
    result = evaluate_phase_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        phase={"id": "plan", "done_when": [PLAN_JSON_PATH]},
        deadline_exceeded=False,
    )
    assert result.passed is False
    assert PLAN_JSON_PATH in result.missing


def test_gate_wrong_phase_done_does_not_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        lambda: _FakeManager({PHASE_DONE_PATH: b"ingest\n", PLAN_JSON_PATH: b"{}"}),
    )
    result = evaluate_phase_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        phase={"id": "plan", "done_when": [PLAN_JSON_PATH]},
        deadline_exceeded=False,
    )
    assert result.passed is False
    assert PHASE_DONE_PATH in result.missing


def test_deadline_does_not_pass() -> None:
    result = evaluate_phase_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        phase={"id": "plan"},
        deadline_exceeded=True,
    )
    assert result.passed is False
    assert "deadline" in result.missing[0]


def test_retry_prompt_lists_missing() -> None:
    text = retry_prompt("plan", [PLAN_JSON_PATH])
    assert "plan" in text
    assert PLAN_JSON_PATH in text


def test_retry_cap_fails_job(monkeypatch) -> None:
    job = _job()
    phase = job.phases[0]
    for _ in range(DEFAULT_PHASE_RETRY_LIMIT):
        increment_gate_retries(phase)
    commits: list[str] = []

    def _commit() -> None:
        commits.append("commit")

    db = SimpleNamespace(commit=_commit)
    monkeypatch.setattr(
        continuation_mod, "_enqueue_or_remember", lambda *_a, **_k: None
    )
    continuation_mod._retry_or_fail_phase(
        db,
        job=job,
        user_id=uuid4(),
        phase=phase,
        missing=[PLAN_JSON_PATH],
    )
    assert job.status == CraftJobStatus.FAILED
    assert job.error_detail is not None
    assert "retry" in job.error_detail.lower()


def test_golden_path_does_not_advance_without_done_when(monkeypatch) -> None:
    """Silent phase advance is a fail. Missing PLAN.json keeps index at 0."""
    job = _job()
    enqueued: list[str] = []
    empty = _FakeManager({})
    for target in (
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=empty: _fake)
    monkeypatch.setattr(
        continuation_mod,
        "get_specialist_for_session",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        continuation_mod,
        "get_open_job_for_session",
        lambda *_a, **_k: job,
    )
    monkeypatch.setattr(
        continuation_mod,
        "job_total_budget_exhausted",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        continuation_mod,
        "_enqueue_or_remember",
        lambda *_args, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    db = SimpleNamespace(commit=lambda: None)
    continuation_mod.maybe_continue_craft_job(
        db,
        session_id=job.session_id,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        turn_succeeded=True,
        deadline_exceeded=False,
        cancelled=False,
    )
    assert job.current_phase_index == 0
    assert job.status == CraftJobStatus.RUNNING
    assert enqueued
    assert "not done" in enqueued[0]


def test_golden_path_advances_only_after_artifacts(monkeypatch) -> None:
    plan = {
        "goal": "two lanes",
        "phases": [
            {"id": "plan", "kind": "plan", "done_when": [PLAN_JSON_PATH]},
            {"id": "analyze", "kind": "analyze"},
            {"id": "compose", "kind": "compose"},
            {"id": "review", "kind": "review"},
        ],
        "lanes": [
            {"role": "a", "output_dir": "project/research/a"},
            {"role": "b", "output_dir": "project/research/b"},
        ],
    }
    import json

    files = {
        PHASE_DONE_PATH: b"plan\n",
        PLAN_JSON_PATH: json.dumps(plan).encode(),
        "outputs/PLAN.md": b"# Plan\n\nTwo lanes.\n",
        "outputs/TODO.md": b"- [x] Write the plan\n",
    }
    job = _job()
    enqueued: list[str] = []
    fake = _FakeManager(files)
    for target in (
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        "onyx.server.features.build.jobs.continuation.get_sandbox_manager",
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.host_workers.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=fake: _fake)
    monkeypatch.setattr(
        continuation_mod,
        "get_specialist_for_session",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        continuation_mod,
        "get_open_job_for_session",
        lambda *_a, **_k: job,
    )
    monkeypatch.setattr(
        continuation_mod,
        "job_total_budget_exhausted",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        continuation_mod,
        "_enqueue_or_remember",
        lambda *_args, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    spawned: list[str] = []

    def _spawn(_db_session, *, job, user_id, state, lanes):  # noqa: ARG001
        job.status = CraftJobStatus.WAITING_LANES
        spawned.extend(node.id for node in lanes)

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._spawn_lanes", _spawn
    )
    db = SimpleNamespace(commit=lambda: None)
    continuation_mod.maybe_continue_craft_job(
        db,
        session_id=job.session_id,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        turn_succeeded=True,
        deadline_exceeded=False,
        cancelled=False,
    )
    assert spawned == ["lane:a", "lane:b"]
    assert job.status == CraftJobStatus.WAITING_LANES
    assert not enqueued


def test_deadline_retries_same_phase(monkeypatch) -> None:
    job = _job()
    empty = _FakeManager({})
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=empty: _fake)
    monkeypatch.setattr(
        continuation_mod,
        "get_specialist_for_session",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        continuation_mod,
        "get_open_job_for_session",
        lambda *_a, **_k: job,
    )
    monkeypatch.setattr(
        continuation_mod,
        "job_total_budget_exhausted",
        lambda *_a, **_k: False,
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        continuation_mod,
        "_enqueue_or_remember",
        lambda *_args, **kwargs: enqueued.append(kwargs["prompt"]) or uuid4(),
    )
    db = SimpleNamespace(commit=lambda: None)
    continuation_mod.maybe_continue_craft_job(
        db,
        session_id=job.session_id,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        turn_succeeded=False,
        deadline_exceeded=True,
        cancelled=False,
    )
    assert job.current_phase_index == 0
    assert job.status == CraftJobStatus.RUNNING
    assert enqueued


def test_retry_limit_error_keeps_a_reason() -> None:
    from onyx.server.features.build.jobs.gates import (
        ContractGateResult,
        GateMissing,
        gate_retry_limit_detail,
        retry_limit_error_detail,
    )

    assert retry_limit_error_detail() == "Phase gate retry limit reached: unknown"
    assert (
        gate_retry_limit_detail(ContractGateResult(passed=False), "review")
        == "Phase gate retry limit reached: review"
    )
    assert (
        gate_retry_limit_detail(
            ContractGateResult(
                passed=False,
                missing=[
                    GateMissing(
                        path="",
                        reason="retry limit reached",
                        owner_node="review",
                    )
                ],
            ),
            "review",
        )
        == "Phase gate retry limit reached: retry limit reached"
    )


def test_parse_review_accepts_done_true() -> None:
    from onyx.server.features.build.jobs.gates import _parse_review

    payload = _parse_review(
        b'{"node":"review","done":true,"verdict":"conditional_defer_no_go"}'
    )
    assert payload["passed"] is True
