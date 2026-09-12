"""Channel reducers merge; a new plan cannot silently overwrite."""

from __future__ import annotations

import pytest

from onyx.server.features.build.jobs.channels import (
    ArtifactRecord,
    JobState,
    PlanChannel,
    apply_writes,
    empty_state,
    strip_postgres_json_nuls,
)


def test_artifact_summary_drops_nul() -> None:
    record = ArtifactRecord(
        path="outputs/a.md",
        producer_node="plan",
        summary="hello\x00world",
    )
    assert record.summary == "helloworld"
    assert "\x00" not in strip_postgres_json_nuls({"summary": "a\x00b"})["summary"]


def test_scan_artifacts_does_not_store_nul_summary(monkeypatch) -> None:
    from uuid import uuid4

    from onyx.server.features.build.jobs.blackboard import scan_artifacts

    files = {
        "outputs/PLAN.md": b"# Plan\nhello\x00world\n",
        "outputs/mcp/hit.bin": b"\x89PNG\r\n\x1a\n\x00\x00binary",
    }

    class _FakeManager:
        def read_file(self, _sandbox_id, _session_id, path: str) -> bytes:
            if path not in files:
                raise FileNotFoundError(path)
            return files[path]

        def list_directory(self, _sandbox_id, _session_id, path: str) -> list[str]:
            prefix = path.rstrip("/") + "/"
            names = [
                key[len(prefix) :]
                for key in files
                if key.startswith(prefix) and "/" not in key[len(prefix) :]
            ]
            if names:
                return names
            raise FileNotFoundError(path)

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.blackboard.get_sandbox_manager",
        lambda: _FakeManager(),
    )
    found = scan_artifacts(
        sandbox_id=uuid4(), session_id=uuid4(), producer_node="plan"
    )
    assert found["outputs/PLAN.md"].summary == "(binary)"
    assert found["outputs/mcp/hit.bin"].summary == "(binary)"
    dumped = {path: record.model_dump(mode="json") for path, record in found.items()}
    assert "\\u0000" not in str(strip_postgres_json_nuls(dumped))


def test_persist_state_strips_nul_from_job_state() -> None:
    from types import SimpleNamespace

    from onyx.server.features.build.jobs.graph import compile_graph
    from onyx.server.features.build.jobs.kernel import persist_state

    job = SimpleNamespace(
        state={},
        phases=[],
        current_phase_index=0,
        domain="general",
    )
    state = apply_writes(
        empty_state(),
        {
            "goal": "goal\x00x",
            "cursor": ["plan"],
            "graph": compile_graph().to_snapshot(),
            "artifacts": {
                "outputs/a.md": {
                    "path": "outputs/a.md",
                    "producer_node": "plan",
                    "summary": "keep\x00nul",
                }
            },
        },
    )
    persist_state(job, state)
    assert job.state["goal"] == "goalx"
    assert job.state["artifacts"]["outputs/a.md"]["summary"] == "keepnul"
    assert "\x00" not in str(job.state)


def test_artifact_and_citation_merge() -> None:
    state = empty_state()
    state = apply_writes(
        state,
        {
            "artifacts": {
                "outputs/a.md": {
                    "path": "outputs/a.md",
                    "producer_node": "analyze",
                    "summary": "a",
                }
            },
            "citations": {"src-1": {"key": "src-1", "title": "One"}},
        },
    )
    state = apply_writes(
        state,
        {
            "artifacts": {
                "outputs/b.md": {
                    "path": "outputs/b.md",
                    "producer_node": "compose",
                    "summary": "b",
                }
            },
            "citations": {"src-2": {"key": "src-2", "title": "Two"}},
        },
    )
    assert set(state.artifacts) == {"outputs/a.md", "outputs/b.md"}
    assert state.citations["src-1"].number == 1
    assert state.citations["src-2"].number == 2


def test_todo_cannot_uncomplete() -> None:
    state = JobState()
    state = apply_writes(
        state,
        {
            "todo": {
                "plan": {
                    "id": "plan",
                    "owner_node": "plan",
                    "status": "succeeded",
                    "title": "Plan",
                }
            }
        },
    )
    state = apply_writes(
        state,
        {
            "todo": {
                "plan": {
                    "id": "plan",
                    "owner_node": "plan",
                    "status": "pending",
                    "title": "Plan",
                }
            }
        },
    )
    assert state.todo["plan"].status == "succeeded"


def test_plan_requires_higher_version() -> None:
    state = apply_writes(
        empty_state(),
        {
            "plan": PlanChannel(
                version=1, goal="first", phases=[], lanes=[], inputs=[]
            ).model_dump()
        },
    )
    with pytest.raises(ValueError, match="version"):
        apply_writes(
            state,
            {
                "plan": PlanChannel(
                    version=1, goal="overwrite", phases=[], lanes=[], inputs=[]
                ).model_dump()
            },
        )
    next_state = apply_writes(
        state,
        {
            "plan": PlanChannel(
                version=2, goal="updated", phases=[], lanes=[], inputs=[]
            ).model_dump()
        },
    )
    assert next_state.plan is not None
    assert next_state.plan.goal == "updated"


def test_reopen_nodes_removes_only_owner() -> None:
    state = apply_writes(
        empty_state(),
        {"completed_nodes": ["plan", "compose", "review"]},
    )
    state = apply_writes(state, {"reopen_nodes": ["compose"]})
    assert state.completed_nodes == ["plan", "review"]


def test_checkpoint_replay_rebuilds_state() -> None:
    from onyx.server.features.build.jobs.channels import apply_writes as apply

    writes = [
        {"goal": "g", "cursor": ["plan"]},
        {
            "completed_nodes": ["plan"],
            "artifacts": {
                "outputs/plan/PLAN.json": {
                    "path": "outputs/plan/PLAN.json",
                    "producer_node": "plan",
                    "summary": "plan",
                }
            },
        },
    ]
    state = empty_state()
    for delta in writes:
        state = apply(state, delta)
    assert state.goal == "g"
    assert "plan" in state.completed_nodes
    assert "outputs/plan/PLAN.json" in state.artifacts
