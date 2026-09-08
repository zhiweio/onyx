"""Host injects disk plan/todo/memory into each long-job brief."""

from __future__ import annotations

from uuid import uuid4

from onyx.server.features.build.jobs.assembler import assemble_brief
from onyx.server.features.build.jobs.channels import ArtifactRecord, empty_state
from onyx.server.features.build.jobs.durability import (
    SEED_PLAN_MD,
    DurabilitySnapshot,
    load_durability_snapshot,
)
from onyx.server.features.build.jobs.gates import retry_brief
from onyx.server.features.build.jobs.graph import GraphNode, compile_graph


class _FakeManager:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def read_file(self, _sandbox_id, _session_id, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def list_directory(self, _sandbox_id, _session_id, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        names = [
            key[len(prefix) :]
            for key in self.files
            if key.startswith(prefix) and "/" not in key[len(prefix) :]
        ]
        if names:
            return names
        raise FileNotFoundError(path)


def test_snapshot_injects_file_bodies_and_cache_index() -> None:
    manager = _FakeManager(
        {
            "outputs/PLAN.md": b"# Plan\n\n## Goal\n\nWrite the memo\n",
            "outputs/TODO.md": b"- [ ] Draft section 1\n- [x] Scope\n",
            "outputs/MEMORY.md": b"PMID 123 is the key paper.\n",
            "outputs/mcp/search.json": b'{"ok": true}\n',
            "outputs/commands/rg.txt": b"hits\n",
        }
    )
    snapshot = load_durability_snapshot(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        manager=manager,
    )
    assert "Write the memo" in snapshot.files["outputs/PLAN.md"]
    assert "outputs/mcp/search.json" in snapshot.caches
    assert "outputs/commands/rg.txt" in snapshot.caches

    node = compile_graph().get("plan")
    assert node is not None
    brief = assemble_brief(
        node=node,
        state=empty_state(),
        job_name="job",
        domain="general",
        user_prompt="goal",
        snapshot=snapshot,
    )
    assert "Write the memo" not in brief
    assert "PMID 123 is the key paper." not in brief
    assert "outputs/PLAN.md" in brief
    assert "outputs/mcp/search.json" not in brief
    assert "outputs/commands/rg.txt" not in brief
    assert "User-visible reply" in brief
    assert "playbook lists optional lanes" not in brief
    assert "\nGoal:" in brief
    assert "\nContext:" in brief
    assert "\nConstraints:" in brief
    assert "\nDone when:" in brief
    assert "Do not list, glob, or find /workspace/sessions" in brief
    assert "Create a directory only when you write a file into it" in brief
    assert "Write PLAN.md and TODO.md with this job's real plan" in brief
    assert "Visible tools in this session" not in brief


def test_empty_snapshot_omits_missing_files() -> None:
    lines = DurabilitySnapshot().format_for_brief()
    assert lines == []
    assert SEED_PLAN_MD.startswith("# Plan")


def test_assemble_brief_names_parallel_search_tool() -> None:
    node = compile_graph().get("plan")
    assert node is not None
    brief = assemble_brief(
        node=node,
        state=empty_state(),
        job_name="job",
        domain="general",
        user_prompt="Use Parallel Search MCP for public web search",
        visible_tools=[
            "parallel-search-382",
            "parallel-search-382_web_search",
            "parallel-search-382_web_fetch",
        ],
    )
    assert "`parallel-search-382_web_search`" in brief
    assert "webfetch" in brief
    assert "Visible tools in this session" not in brief
    assert "outputs/mcp/" not in brief


def test_lane_brief_names_search_and_skips_inventory() -> None:
    node = GraphNode(
        id="lane:literature",
        kind="lane",
        name="Literature",
        worker="opencode_turn",
        role="literature",
        skill_id="biomed-literature",
        required_paths=["outputs/lanes/literature/NOTES.md"],
    )
    state = empty_state()
    state.artifacts["outputs/research/notes.md"] = ArtifactRecord(
        path="outputs/research/notes.md",
        nonempty=True,
        summary="cached notes",
    )
    snapshot = DurabilitySnapshot(files={"outputs/PLAN.md": "# Plan\nWrite memo\n"})
    brief = assemble_brief(
        node=node,
        state=state,
        job_name="job",
        domain="biomed",
        user_prompt="Use Parallel Search MCP for public web search",
        snapshot=snapshot,
        visible_tools=[
            "parallel-search-382",
            "parallel-search-382_web_search",
            "parallel-search-382_web_fetch",
        ],
    )
    assert "`parallel-search-382_web_search`" in brief
    assert "Readable artifacts" not in brief
    assert "On disk:" not in brief
    assert "outputs/PLAN.md" not in brief
    assert "outputs/research/notes.md" not in brief


def test_retry_brief_search_reason_leads_with_search() -> None:
    text = retry_brief(
        "lane:literature",
        ["outputs/lanes/literature/NOTES.md"],
        reasons=["search required but no verifiable citation"],
    )
    assert text.index("Call `parallel-search-*_web_search`") < text.index(
        "then write the notes"
    )
    assert not text.lstrip().startswith("Write only the missing artifacts")
    assert "Write only the missing artifacts" not in text


def test_retry_brief_missing_files_keeps_write_action() -> None:
    text = retry_brief("plan", ["outputs/PLAN.json"])
    assert "Write only the missing artifacts" in text
