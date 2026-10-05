"""Unit tests for the P5 memory helpers that need no database."""

from __future__ import annotations

from uuid import uuid4

from onyx.db.long_term_memory import RecalledMemory
from onyx.db.models import CraftProject, User
from onyx.memory.long_term import (
    effective_memory_enabled,
    render_memory_markdown,
)


def _user(craft_flag: bool) -> User:
    return User(craft_use_long_term_memory=craft_flag)


def _project(enabled: bool) -> CraftProject:
    return CraftProject(memory_enabled=enabled)


def test_effective_memory_enabled_truth_table() -> None:
    # Global per-user flag wins regardless of project.
    assert effective_memory_enabled(_user(True), None) is True
    assert effective_memory_enabled(_user(True), _project(False)) is True
    # Project switch enables when the user flag is off.
    assert effective_memory_enabled(_user(False), _project(True)) is True
    # Both off → memoryless.
    assert effective_memory_enabled(_user(False), None) is False
    assert effective_memory_enabled(_user(False), _project(False)) is False


def _memory(text: str, project_id) -> RecalledMemory:
    return RecalledMemory(
        id=1,
        text=text,
        kind="semantic",
        source="agent",
        source_surface="craft",
        project_id=project_id,
        distance=0.1,
    )


def test_render_memory_markdown_sections_and_banner() -> None:
    project_id = uuid4()
    md = render_memory_markdown(
        [_memory("prefers tables", None), _memory("uses 13% VAT", project_id)],
        project_id,
    )
    assert "untrusted" in md
    assert "Project memories" in md
    assert "user memories" in md
    assert "- prefers tables" in md
    assert "- uses 13% VAT" in md
    # Ordering: project section before user section.
    assert md.index("Project memories") < md.index("user memories")


def test_render_memory_markdown_empty_returns_empty() -> None:
    assert render_memory_markdown([], None) == ""
