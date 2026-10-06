"""Skill-subset slug computation: user-picked skill UUIDs resolve to the
runtime slugs that exist under the sandbox's managed skills root."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from onyx.server.features.build.skills_subset import compute_session_skill_slugs


class _StubSession:
    """Minimal stand-in: the patched resolver never touches the DB."""


def test_selected_skill_uuids_resolve_to_slugs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A picked chip sent as a skill UUID must link the skill's slug, not a
    dangling ``.opencode/skills/<uuid>`` symlink."""
    import onyx.server.features.build.skills_subset as subset

    skill_row_id = uuid4()

    def fake_resolve(_db_session: Any, refs: list[str]) -> list[str]:
        assert str(skill_row_id) in refs
        return ["dingtalk"]

    monkeypatch.setattr(subset, "resolve_skill_refs_to_slugs", fake_resolve)

    result = compute_session_skill_slugs(
        _StubSession(),  # ty: ignore[invalid-argument-type]
        user=object(),  # ty: ignore[invalid-argument-type]
        selected_skill_ids=[str(skill_row_id)],
        visible={"dingtalk", "docx"},
    )

    assert "dingtalk" in result
    assert str(skill_row_id) not in result
