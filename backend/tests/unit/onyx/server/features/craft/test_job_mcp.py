from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

from onyx.db.enums import CraftJobStatus
from onyx.db.models import CraftJob
from onyx.server.features.build.jobs.channels import JobState
from onyx.server.features.build.jobs.graph import compile_graph
from onyx.server.features.build.jobs.kernel import initialize_job_state, load_state
from onyx.server.features.build.jobs.mcp import (
    job_picker_selection,
    resolve_job_mcp_server_ids,
)


def _job(
    *,
    selected_skill_ids: list[str] | None = None,
    selected_mcp_server_ids: list[int] | None = None,
) -> CraftJob:
    state = JobState(
        goal="goal",
        selected_skill_ids=selected_skill_ids or [],
        selected_mcp_server_ids=selected_mcp_server_ids or [],
    )
    return cast(
        CraftJob,
        SimpleNamespace(
            id=uuid4(),
            status=CraftJobStatus.RUNNING,
            state=state.model_dump(mode="json"),
        ),
    )


def test_empty_job_picker_keeps_all_eligible_servers() -> None:
    job = _job()
    assert job_picker_selection(job) == ([], [])
    assert resolve_job_mcp_server_ids(MagicMock(), MagicMock(), job) is None


def test_job_picker_selection_reads_state() -> None:
    job = _job(
        selected_skill_ids=["hithink-finance"],
        selected_mcp_server_ids=[12, 13],
    )
    assert job_picker_selection(job) == (["hithink-finance"], [12, 13])


def test_initialize_job_state_stores_picker() -> None:
    graph = compile_graph("tax")
    job = cast(
        CraftJob,
        SimpleNamespace(
            domain="tax",
            name="job",
            phases=graph.to_phase_list(),
            current_phase_index=0,
            state={},
            status=CraftJobStatus.RUNNING,
        ),
    )
    initialize_job_state(
        job,
        goal="analyze",
        selected_skill_ids=["hithink-finance"],
        selected_mcp_server_ids=[12, 13],
    )
    stored = load_state(job)
    assert stored.selected_skill_ids == ["hithink-finance"]
    assert stored.selected_mcp_server_ids == [12, 13]


def test_job_with_picker_resolves_effective_ids(monkeypatch) -> None:
    job = _job(
        selected_skill_ids=["hithink-finance"],
        selected_mcp_server_ids=[12],
    )
    captured: dict[str, object] = {}

    def fake_resolve(_db, _user, **kwargs):
        captured.update(kwargs)
        return [12, 14]

    monkeypatch.setattr(
        "onyx.server.features.build.jobs.mcp.resolve_effective_mcp_server_ids",
        fake_resolve,
    )
    assert resolve_job_mcp_server_ids(MagicMock(), MagicMock(), job) == [12, 14]
    assert captured["selected_skill_ids"] == ["hithink-finance"]
    assert captured["selected_mcp_server_ids"] == [12]
