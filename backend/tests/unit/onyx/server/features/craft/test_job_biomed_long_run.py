"""Simulate a full biomed long job: GLP-1 initiation research report."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.orm import Session

from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
from onyx.db.models import CraftJob
from onyx.server.features.build.jobs.graph import compile_graph
from onyx.server.features.build.jobs.kernel import (
    after_lane_turn,
    after_worker_turn,
    initialize_job_state,
    load_state,
    persist_state,
    resume_job,
)
from onyx.server.features.build.jobs.models import CraftJobResponse

GOAL = (
    "撰写一份 GLP-1 受体激动剂创新药立项深度研究报告，覆盖文献、临床、"
    "专利自由实施与 CMC 质量。"
)
ROLES = ("literature", "clinical", "patent", "cmc")
QUESTIONS = {
    "literature": "What efficacy signals exist for oral GLP-1 agonists?",
    "clinical": "Which Phase 2 designs fit a once-daily oral GLP-1?",
    "patent": "What freedom-to-operate gaps remain in the oral GLP-1 space?",
    "cmc": "What CMC risks block first-in-human supply of an oral GLP-1?",
}


class _FakeManager:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def read_file(self, _sandbox_id: object, _session_id: object, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def list_directory(
        self, _sandbox_id: object, _session_id: object, path: str
    ) -> list[str]:
        prefix = path.rstrip("/") + "/"
        if any(key.startswith(prefix) or key == path for key in self.files):
            return ["ok"]
        raise FileNotFoundError(path)

    def write_files_to_sandbox(self, **kwargs: object) -> None:
        files = kwargs.get("files")
        if not isinstance(files, dict):
            return
        for path, raw in files.items():
            if isinstance(raw, (bytes, bytearray)):
                self.files[str(path)] = bytes(raw)


def _job() -> Any:
    graph = compile_graph("biomed")
    job = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        domain="biomed",
        name="GLP-1 initiation report",
        status=CraftJobStatus.RUNNING,
        phases=graph.to_phase_list(),
        current_phase_index=0,
        state={},
        started_at=None,
        total_budget_seconds=7200,
        phase_budget_seconds=1500,
        error_detail=None,
        specialists=[],
        project_id=uuid4(),
        scenario_id=None,
        drain_reason=None,
        events=[],
    )
    initialize_job_state(cast(CraftJob, job), goal=GOAL)
    return job


def _db() -> Session:
    return cast(
        Session, SimpleNamespace(commit=lambda: None, add=lambda *_a, **_k: None)
    )


def _patch_sandbox(monkeypatch: Any, manager: _FakeManager) -> None:
    for target in (
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        "onyx.server.features.build.jobs.kernel.get_sandbox_manager",
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        "onyx.server.features.build.jobs.host_workers.get_sandbox_manager",
        "onyx.server.features.build.jobs.reconcile.get_sandbox_manager",
    ):
        monkeypatch.setattr(target, lambda _fake=manager: _fake)


def _plan_bytes() -> bytes:
    plan = {
        "goal": GOAL,
        "phases": [
            {"id": "plan", "kind": "plan", "name": "Plan"},
            {
                "id": "compose",
                "kind": "compose",
                "name": "Compose",
                "done_when": ["outputs/markdown/report.md"],
            },
            {
                "id": "review",
                "kind": "review",
                "name": "Review",
                "done_when": ["outputs/review/REVIEW.json"],
            },
        ],
        "lanes": [
            {
                "role": role,
                "output_dir": f"outputs/lanes/{role}",
                "questions": [QUESTIONS[role]],
            }
            for role in ROLES
        ],
        "inputs": [],
        "ask_delivery": True,
    }
    return json.dumps(plan, ensure_ascii=False).encode()


def _findings(role: str) -> bytes:
    question = QUESTIONS[role]
    return (
        f"# {role} findings\n\n"
        f"{question}\n\n"
        f"Answer: simulated evidence for an oral GLP-1 initiation case. [1]\n"
        f"Source: project/extracted/{role}-note.pdf\n"
    ).encode()


def _report() -> bytes:
    return (
        "# GLP-1 创新药立项深度研究报告\n\n"
        "## 结论\n"
        "口服 GLP-1 有可立项的疗效信号，但 FTO 与 CMC 供应仍是闸门。[1]\n\n"
        "## 分路对账\n"
        "文献、临床、专利与 CMC 四路已覆盖计划问题。\n"
    ).encode()


def _review(*, passed: bool, missing: list[dict[str, str]] | None = None) -> bytes:
    payload = {
        "passed": passed,
        "missing": missing or [],
        "conflicts": [],
        "coverage": 1.0 if passed else 0.5,
    }
    return json.dumps(payload).encode()


def test_full_glp1_initiation_job_succeeds(monkeypatch: Any) -> None:
    files: dict[str, bytes] = {}
    manager = _FakeManager(files)
    _patch_sandbox(monkeypatch, manager)
    sandbox_id = uuid4()
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(str(kwargs["prompt"])) or uuid4(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._sandbox_id_for_session",
        lambda *_a, **_k: sandbox_id,
    )

    def _spawn(
        _db_session: Session,
        *,
        job: Any,
        user_id: object,
        state: object,
        lanes: list[Any],
    ) -> None:
        _ = (user_id, state)
        from onyx.server.features.build.jobs.channels import apply_writes
        from onyx.server.features.build.jobs.kernel import persist_state as persist

        job.status = CraftJobStatus.WAITING_LANES
        job.specialists = [
            SimpleNamespace(
                id=uuid4(),
                session_id=uuid4(),
                status=CraftJobSpecialistStatus.RUNNING,
                node_id=node.id,
                role=node.role,
                error_detail=None,
            )
            for node in lanes
        ]
        persist(
            job,
            apply_writes(
                load_state(job),
                {"cursor": [node.id for node in lanes], "last_node": lanes[0].id},
            ),
        )

    monkeypatch.setattr("onyx.server.features.build.jobs.kernel._spawn_lanes", _spawn)

    job = _job()
    db = _db()
    user_id = uuid4()

    files["outputs/plan/PLAN.json"] = _plan_bytes()
    files["outputs/PLAN.md"] = b"# Plan\n\nGLP-1 initiation.\n"
    files["outputs/TODO.md"] = b"- [x] Write the plan\n"
    after_worker_turn(
        db,
        job=cast(CraftJob, job),
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert job.status == CraftJobStatus.WAITING_LANES
    state = load_state(job)
    assert "plan" in state.completed_nodes
    assert state.interrupt is None
    assert state.plan is not None
    assert len(state.plan.lanes) == 4
    assert {row.node_id for row in job.specialists} == {
        f"lane:{role}" for role in ROLES
    }

    for index, role in enumerate(ROLES):
        files[f"outputs/lanes/{role}/NOTES.md"] = _findings(role)
        job.specialists[index].status = CraftJobSpecialistStatus.SUCCEEDED
        after_lane_turn(
            db,
            job=cast(CraftJob, job),
            user_id=user_id,
            specialist_ok=True,
            node_id=f"lane:{role}",
        )
        if index < len(ROLES) - 1:
            assert job.status == CraftJobStatus.WAITING_LANES

    state = load_state(job)
    for role in ROLES:
        assert f"lane:{role}" in state.completed_nodes
    assert "reconcile" in state.completed_nodes
    assert "outputs/reconcile/RECONCILE.json" in files
    assert enqueued
    assert any("compose" in prompt for prompt in enqueued)

    files["outputs/markdown/report.md"] = _report()
    after_worker_turn(
        db,
        job=cast(CraftJob, job),
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    state = load_state(job)
    assert "compose" in state.completed_nodes
    assert any("review" in prompt for prompt in enqueued)

    files["outputs/review/REVIEW.json"] = _review(passed=True)
    after_worker_turn(
        db,
        job=cast(CraftJob, job),
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert job.status == CraftJobStatus.INTERRUPTED
    state = load_state(job)
    assert "review" in state.completed_nodes
    assert state.interrupt is not None
    assert state.interrupt.kind == "approve_delivery"
    resume_job(db, job=cast(CraftJob, job), user_id=user_id, sandbox_id=sandbox_id)
    assert job.status == CraftJobStatus.SUCCEEDED
    assert state.citations
    payload = CraftJobResponse.from_model(cast(CraftJob, job))
    kinds = [item.kind for item in payload.timeline]
    assert kinds == ["plan", "lane", "reconcile", "compose", "review"]
    assert {item.status for item in payload.timeline} == {"succeeded"}
    summaries = [item.summary for item in payload.artifacts if item.summary]
    assert any("GLP-1" in summary or "立项" in summary for summary in summaries)


def test_review_gap_then_pass_finishes_job(monkeypatch: Any) -> None:
    from onyx.server.features.build.jobs.plan import parse_plan

    files: dict[str, bytes] = {
        "outputs/markdown/report.md": _report(),
        "outputs/review/REVIEW.json": _review(
            passed=False,
            missing=[
                {
                    "path": "outputs/markdown/report.md",
                    "reason": "missing CMC supply table",
                    "owner_node": "compose",
                }
            ],
        ),
    }
    manager = _FakeManager(files)
    _patch_sandbox(monkeypatch, manager)
    enqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation._enqueue_or_remember",
        lambda *_a, **kwargs: enqueued.append(str(kwargs["prompt"])) or uuid4(),
    )
    job = _job()
    state = load_state(job)
    state.graph = compile_graph(
        "biomed", parse_plan(json.loads(_plan_bytes().decode()))
    ).to_snapshot()
    state.completed_nodes = [
        "plan",
        "lane:literature",
        "lane:clinical",
        "lane:patent",
        "lane:cmc",
        "reconcile",
        "compose",
    ]
    state.last_node = "review"
    state.cursor = ["review"]
    persist_state(cast(CraftJob, job), state)

    after_worker_turn(
        _db(),
        job=cast(CraftJob, job),
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    state = load_state(job)
    assert "compose" not in state.completed_nodes
    assert state.last_node == "compose"
    assert job.status != CraftJobStatus.SUCCEEDED
    assert any(
        "missing" in prompt.lower() or "compose" in prompt for prompt in enqueued
    )

    files["outputs/review/REVIEW.json"] = _review(passed=True)
    state.completed_nodes = [
        item for item in state.completed_nodes if item != "review"
    ] + ["compose"]
    state.last_node = "review"
    persist_state(cast(CraftJob, job), state)
    db = _db()
    user_id = uuid4()
    sandbox_id = uuid4()
    after_worker_turn(
        db,
        job=cast(CraftJob, job),
        user_id=user_id,
        sandbox_id=sandbox_id,
        session_id=job.session_id,
        deadline_exceeded=False,
    )
    assert job.status == CraftJobStatus.INTERRUPTED
    resume_job(db, job=cast(CraftJob, job), user_id=user_id, sandbox_id=sandbox_id)
    assert job.status == CraftJobStatus.SUCCEEDED
