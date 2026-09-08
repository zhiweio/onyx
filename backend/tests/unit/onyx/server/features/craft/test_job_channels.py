"""Channel reducers merge; a new plan cannot silently overwrite."""

from __future__ import annotations

import pytest

from onyx.server.features.build.jobs.channels import (
    JobState,
    PlanChannel,
    apply_writes,
    empty_state,
)


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
