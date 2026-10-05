"""P1 correctness: graph validation, scenario contract, subset, usage."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from onyx.server.features.build.jobs.graph import (
    GraphNode,
    JobGraph,
    PlanValidationError,
    compile_graph,
)
from onyx.server.features.build.jobs.plan import JobPlan
from onyx.server.features.build.jobs.turn_errors import is_transient_turn_error
from onyx.server.features.build.sandbox.opencode.serve_client import (
    _context_usage_from_info,
)
from onyx.server.features.build.sandbox.session_workspace import (
    build_skills_link_snippet,
)
from onyx.server.features.scenario.bindings import compile_scenario_plan


def _lane_plan(**overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "goal": "test goal",
        "lanes": [
            {"role": "a", "done_when": ["outputs/lanes/a/NOTES.md"]},
            {"role": "b", "done_when": ["outputs/lanes/b/NOTES.md"]},
        ],
    }
    plan.update(overrides)
    return plan


def test_cycle_plan_rejected() -> None:
    raw = _lane_plan(
        lanes=[
            {
                "role": "a",
                "depends_on": ["b"],
                "done_when": ["outputs/lanes/a/NOTES.md"],
            },
            {
                "role": "b",
                "depends_on": ["a"],
                "done_when": ["outputs/lanes/b/NOTES.md"],
            },
        ]
    )
    with pytest.raises(PlanValidationError) as excinfo:
        compile_graph("tax", plan=JobPlan.model_validate(raw))
    assert "cycle" in str(excinfo.value).lower()


def test_valid_lane_chain_compiles() -> None:
    raw = _lane_plan(
        lanes=[
            {"role": "a", "done_when": ["outputs/lanes/a/NOTES.md"]},
            {
                "role": "b",
                "depends_on": ["a"],
                "done_when": ["outputs/lanes/b/NOTES.md"],
            },
        ]
    )
    graph = compile_graph("tax", plan=JobPlan.model_validate(raw))
    assert [node.id for node in graph.nodes] == [
        "plan",
        "lane:a",
        "lane:b",
        "reconcile",
        "work",
    ]
    assert graph.warnings == []


def test_unresolvable_dep_dropped_with_warning() -> None:
    raw = _lane_plan(
        lanes=[
            {
                "role": "a",
                "depends_on": ["ghost"],
                "done_when": ["outputs/lanes/a/NOTES.md"],
            },
            {"role": "b", "done_when": ["outputs/lanes/b/NOTES.md"]},
        ]
    )
    graph = compile_graph("tax", plan=JobPlan.model_validate(raw))
    assert any("ghost" in warning for warning in graph.warnings)


def test_deliverables_own_a_terminal_node_when_phases_exist() -> None:
    raw = {
        "goal": "test goal",
        "phases": [{"id": "analyze", "kind": "phase"}],
        "done_when": ["outputs/report/final.docx"],
    }
    graph = compile_graph("tax", plan=JobPlan.model_validate(raw))
    delivery = next((node for node in graph.nodes if node.id == "delivery"), None)
    assert delivery is not None
    assert delivery.required_paths == ["outputs/report/final.docx"]


def test_no_delivery_node_without_done_when() -> None:
    raw = {
        "goal": "test goal",
        "phases": [{"id": "analyze", "done_when": ["outputs/analysis/NOTES.md"]}],
    }
    graph = compile_graph("tax", plan=JobPlan.model_validate(raw))
    assert all(node.id != "delivery" for node in graph.nodes)


def _stalled_graph() -> JobGraph:
    # Snapshot-loaded graphs bypass compile validation, so a corrupt state
    # can still hold a cycle; the dispatcher must fail loudly, not succeed.
    return JobGraph(
        nodes=[
            GraphNode(id="plan", kind="plan", name="Plan", worker="opencode_turn"),
            GraphNode(
                id="lane:a",
                kind="lane",
                name="A",
                worker="opencode_turn",
                depends_on=["lane:b"],
            ),
            GraphNode(
                id="lane:b",
                kind="lane",
                name="B",
                worker="opencode_turn",
                depends_on=["lane:a"],
            ),
        ]
    )


def _stalled_job_state() -> dict[str, Any]:
    graph = _stalled_graph()
    return {
        "goal": "g",
        "completed_nodes": ["plan"],
        "cursor": [],
        "last_node": "plan",
        "graph": graph.to_snapshot(),
    }


class _NoRowsQuery:
    def filter(self, *_args: object, **_kwargs: object) -> "_NoRowsQuery":
        return self

    def first(self) -> None:
        return None


def _db() -> Any:
    return SimpleNamespace(
        commit=lambda: None,
        add=lambda *_a, **_k: None,
        query=lambda *_a, **_k: _NoRowsQuery(),
        rollback=lambda: None,
    )


def _job(state: dict[str, Any]) -> Any:
    from onyx.db.enums import CraftJobStatus

    return SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        domain="tax",
        name="stalled",
        status=CraftJobStatus.RUNNING,
        phases=[],
        current_phase_index=0,
        state=state,
        total_budget_seconds=600,
        phase_budget_seconds=300,
        error_detail=None,
        specialists=[],
        project_id=None,
        scenario_id=None,
    )


def test_stalled_graph_fails_not_succeeds(monkeypatch) -> None:
    from onyx.db.enums import CraftJobStatus
    from onyx.server.features.build.jobs import kernel

    job = _job(_stalled_job_state())
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.emit",
        lambda _db, **kwargs: events.append(
            (kwargs["event_type"], kwargs.get("payload") or {})
        ),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.mark_job_finished",
        lambda j, **kwargs: (
            setattr(j, "status", kwargs.get("status", CraftJobStatus.FAILED)),
            setattr(j, "error_detail", kwargs.get("error_detail")),
        ),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._persist_job_failure_row",
        lambda *_a, **_k: None,
    )
    state = kernel.load_state(job)
    kernel._dispatch_next(
        _db(),
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        state=state,
    )
    assert job.status == CraftJobStatus.FAILED
    assert "stalled" in (job.error_detail or "")
    assert any(event_type == "run.drain" for event_type, _ in events)


def test_completed_graph_still_succeeds(monkeypatch) -> None:
    from onyx.db.enums import CraftJobStatus
    from onyx.server.features.build.jobs import kernel

    state_dict = _stalled_job_state()
    state_dict["completed_nodes"] = ["plan", "lane:a", "lane:b"]
    job = _job(state_dict)
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.mark_job_finished",
        lambda j, **_k: setattr(j, "status", CraftJobStatus.SUCCEEDED),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._notify_job_finished",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._persist_job_workspace",
        lambda *_a, **_k: None,
    )
    state = kernel.load_state(job)
    kernel._dispatch_next(
        _db(),
        job=job,
        user_id=uuid4(),
        sandbox_id=uuid4(),
        session_id=job.session_id,
        state=state,
    )
    assert job.status == CraftJobStatus.SUCCEEDED


def test_scenario_contract_compilation() -> None:
    rules = {
        "domain": "tax",
        "phases": [
            {"id": "collect", "done_when": "报告已撰写完成"},
            {"id": "analyze", "done_when": "outputs/analysis/NOTES.md"},
            {"id": "deliver", "bindings": {"gate": "approve_plan"}},
        ],
        "deliverables": ["outputs/report/final.docx"],
    }
    plan = compile_scenario_plan(rules, goal="年度财税风险报告")
    assert plan.ask_plan is True
    collect = next(phase for phase in plan.phases if phase.id == "collect")
    assert collect.done_when == []
    assert "报告" in collect.notes
    analyze = next(phase for phase in plan.phases if phase.id == "analyze")
    assert analyze.done_when == ["outputs/analysis/NOTES.md"]

    graph = compile_graph("tax", plan=plan)
    plan_node = next(node for node in graph.nodes if node.id == "plan")
    assert plan_node.hitl == "approve_plan"
    delivery = next(node for node in graph.nodes if node.id == "delivery")
    assert delivery.required_paths == ["outputs/report/final.docx"]
    collect_node = next(node for node in graph.nodes if node.id == "collect")
    assert "报告" in collect_node.notes


def test_transient_error_classification() -> None:
    assert is_transient_turn_error("Lane inactive")
    assert is_transient_turn_error("Event bus closed mid-turn")
    assert is_transient_turn_error("Upstream_Error: 502")
    assert not is_transient_turn_error("validation failed")
    assert not is_transient_turn_error(None)


def test_skills_link_snippet_subset_and_fallback() -> None:
    subset = build_skills_link_snippet(
        "/workspace/sessions/x", ["docx", "pptx", "../evil", "caishui-skill"]
    )
    assert "mkdir -p /workspace/sessions/x/.opencode/skills" in subset
    assert "/managed/skills/docx" in subset
    assert "/managed/skills/pptx" in subset
    assert "/managed/skills/caishui-skill" in subset
    assert "evil" not in subset
    assert "rm -rf" in subset

    fallback = build_skills_link_snippet("/workspace/sessions/x", None)
    assert fallback.strip() == (
        "ln -sfn /workspace/managed/skills /workspace/sessions/x/.opencode/skills"
    )

    unsafe_only = build_skills_link_snippet("/workspace/sessions/x", ["../evil"])
    assert unsafe_only == fallback


def test_context_usage_granular_extraction() -> None:
    packet = _context_usage_from_info(
        {
            "id": "msg_123",
            "tokens": {
                "input": 1000,
                "output": 200,
                "reasoning": 50,
                "cache": {"read": 300, "write": 40},
            },
            "cost": 0.0123,
        },
        message_id="msg_123",
    )
    assert packet is not None
    assert packet.used_tokens == 1590
    assert packet.message_id == "msg_123"
    assert packet.input_tokens == 1000
    assert packet.output_tokens == 200
    assert packet.reasoning_tokens == 50
    assert packet.cache_read_tokens == 300
    assert packet.cache_write_tokens == 40
    assert packet.cost == pytest.approx(0.0123)


def test_context_usage_summary_messages_skipped() -> None:
    assert _context_usage_from_info({"summary": True, "tokens": {"input": 1}}) is None
    assert _context_usage_from_info({"tokens": "junk"}) is None


class _FakeLock:
    def __init__(self) -> None:
        self.acquired = False

    def acquire(self, *_args: object, **_kwargs: object) -> bool:
        self.acquired = True
        return True

    def release(self) -> None:
        return None


class _FakeCache:
    def lock(self, *_args: object, **_kwargs: object) -> _FakeLock:
        return _FakeLock()


def test_self_heal_reaps_stale_lane_and_retries(monkeypatch) -> None:
    """WAITING_LANES + a lane whose driver died: the keeper reaps it, and
    the settlement re-drives the lane (transient) instead of failing."""
    import datetime as dt

    from onyx.db.enums import CraftJobSpecialistStatus, CraftJobStatus
    from onyx.server.features.build.jobs import kernel

    graph = compile_graph(
        "tax",
        plan=JobPlan.model_validate(
            {
                "goal": "g",
                "lanes": [{"role": "a", "done_when": ["outputs/lanes/a/NOTES.md"]}],
            }
        ),
    )
    state = {
        "goal": "g",
        "completed_nodes": ["plan", "ingest"],
        "cursor": ["lane:a"],
        "last_node": "lane:a",
        "graph": graph.to_snapshot(),
        "selected_skill_ids": [],
    }
    stale = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(hours=2)
    specialist = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        role="a",
        prompt="",
        node_id="lane:a",
        checkpoint_ns="node:lane:a",
        input_digest="",
        output_artifact_ids=[],
        status=CraftJobSpecialistStatus.RUNNING,
        error_detail=None,
        created_at=stale,
        finished_at=None,
    )
    job = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        domain="tax",
        name="keeper",
        status=CraftJobStatus.WAITING_LANES,
        phases=[],
        current_phase_index=0,
        state=state,
        total_budget_seconds=600,
        phase_budget_seconds=300,
        error_detail=None,
        specialists=[specialist],
        project_id=None,
        scenario_id=None,
    )

    reenqueued: list[str] = []
    monkeypatch.setattr(
        "onyx.cache.factory.get_cache_backend", lambda *_a, **_k: _FakeCache()
    )
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.state.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.continuation.enqueue_job_phase_turn",
        lambda *_a, **kwargs: reenqueued.append(kwargs.get("prompt", "")) or uuid4(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._sandbox_id_for_session",
        lambda *_a, **_k: uuid4(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel._persist_job_workspace",
        lambda *_a, **_k: None,
    )

    db = SimpleNamespace(
        commit=lambda: None,
        add=lambda *_a, **_k: None,
        rollback=lambda: None,
        get=lambda *_a, **_k: None,
        query=lambda *_a, **_k: _NoRowsQuery(),
    )
    from sqlalchemy.orm import Session

    kernel.maybe_self_heal_job(
        cast(Session, db), job=cast(Any, job), user_id=job.user_id
    )

    # The stale lane settled through the transient path: one retry turn,
    # the specialist back to RUNNING, the job still waiting on lanes.
    assert len(reenqueued) == 1
    assert specialist.status == CraftJobSpecialistStatus.RUNNING
    assert job.status == CraftJobStatus.WAITING_LANES
