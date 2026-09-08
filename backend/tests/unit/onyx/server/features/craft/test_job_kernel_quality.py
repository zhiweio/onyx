"""Generic citation, coverage, and HITL budget helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from onyx.db.models import CraftJob
from onyx.server.features.build.jobs.gates import has_citation_marker
from onyx.server.features.build.jobs.graph import GraphNode
from onyx.server.features.build.jobs.reconcile import (
    _answered_questions,
    _blackboard_markdown,
)


def test_citation_marker_is_generic() -> None:
    assert has_citation_marker("See https://pubmed.ncbi.nlm.nih.gov/1")
    assert has_citation_marker("Result [1] supports the claim")
    assert has_citation_marker("Source [NCT01234567]")
    assert not has_citation_marker("No sources, invented numbers.")


def test_coverage_uses_question_text_not_prefix() -> None:
    question = "What freedom-to-operate gaps remain in the oral GLP-1 space?"
    text = (
        "# Findings\n\n"
        "What freedom-to-operate gaps remain in the oral GLP-1 space?\n"
        "Answer: several composition claims remain open. [1]\n"
    )
    assert _answered_questions(text, [question]) == 1
    unanswered = (
        "# Findings\n\n"
        "## Unanswered\n"
        f"{question}\n"
    )
    assert _answered_questions(unanswered, [question]) == 0


def test_blackboard_lists_paths_and_conflicts() -> None:
    markdown = _blackboard_markdown(
        {
            "coverage": 1.0,
            "citation_count": 2,
            "lanes": [
                {
                    "role": "literature",
                    "path": "outputs/lanes/literature/NOTES.md",
                    "answered": 1,
                    "asked": 1,
                }
            ],
            "conflicts": [{"kind": "coverage", "detail": "gap"}],
        }
    )
    assert "outputs/lanes/literature/NOTES.md" in markdown
    assert "coverage: gap" in markdown.lower() or "gap" in markdown


def test_job_elapsed_subtracts_hitl_pause() -> None:
    from onyx.db.craft_job import job_elapsed_seconds, job_total_budget_exhausted

    now = datetime.now(timezone.utc)
    job = cast(
        CraftJob,
        SimpleNamespace(
            started_at=now - timedelta(hours=2),
            total_budget_seconds=3600,
            state={
                "paused_seconds": 0,
                "pause_started_at": (now - timedelta(hours=1, minutes=30)).isoformat(),
            },
        ),
    )
    elapsed = job_elapsed_seconds(job, now=now)
    assert elapsed < 60 * 40
    assert job_total_budget_exhausted(job) is False


def test_empty_lane_required_paths_fail_gate() -> None:
    from onyx.server.features.build.jobs.gates import evaluate_contract_gate

    node = GraphNode(
        id="lane:literature",
        kind="lane",
        name="Literature",
        worker="opencode_turn",
        required_paths=[],
    )
    gate = evaluate_contract_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        node=node,
        deadline_exceeded=False,
    )
    assert gate.passed is False
    assert any(item.reason == "missing or empty" for item in gate.missing)


def test_lane_out_of_bounds_write_fails_gate(monkeypatch) -> None:
    from onyx.server.features.build.jobs.gates import evaluate_contract_gate

    files = {
        "outputs/lanes/literature/NOTES.md": b"See https://example.com [1]\n",
        "outputs/DONE.json": b'{"done": true}\n',
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

    manager = _FakeManager()
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.gates.get_sandbox_manager",
        lambda: manager,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.phase_gate.get_sandbox_manager",
        lambda: manager,
    )
    node = GraphNode(
        id="lane:literature",
        kind="lane",
        name="Literature",
        worker="opencode_turn",
        required_paths=["outputs/lanes/literature/NOTES.md"],
    )
    gate = evaluate_contract_gate(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        node=node,
        deadline_exceeded=False,
    )
    assert gate.passed is False
    assert any("outside" in item.reason for item in gate.missing)


def test_assemble_brief_names_lane_skill() -> None:
    from onyx.server.features.build.jobs.assembler import assemble_brief
    from onyx.server.features.build.jobs.channels import empty_state

    node = GraphNode(
        id="lane:literature",
        kind="lane",
        name="Literature",
        worker="opencode_turn",
        role="literature",
        skill_id="biomed-literature",
        required_paths=["outputs/lanes/literature/NOTES.md"],
    )
    brief = assemble_brief(
        node=node,
        state=empty_state(),
        job_name="job",
        domain="biomed",
    )
    assert "`biomed-literature`" in brief
    assert "long-job-protocol" not in brief
