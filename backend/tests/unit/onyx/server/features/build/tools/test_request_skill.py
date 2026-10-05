"""P3 request_skill: mid-turn skill linking + catalog-dirty lifecycle."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.implementations import (
    RequestSkillTool,
    take_skill_catalog_dirty,
)

CTX = ToolContext(user_id=str(uuid4()))


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int = 0) -> None:  # noqa: ARG002
        self.store[key] = value

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


@pytest.fixture()
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> _FakeCache:
    cache = _FakeCache()

    def _factory(*_args: Any, **_kwargs: Any) -> _FakeCache:
        return cache

    monkeypatch.setattr("onyx.cache.factory.get_cache_backend", _factory)
    return cache


def _patch_lookup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    visible: set[str],
    session: Any,
    sandbox: Any,
    extend_result: bool = True,
) -> list[str]:
    """Patch the DB/session lookups the tool performs."""
    calls: list[str] = []

    class _Mgr:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def extend_session_skills(self, sandbox_arg, session_arg, slugs):  # noqa: ARG002
            calls.extend(slugs)
            return extend_result

    monkeypatch.setattr(
        "onyx.db.users.fetch_user_by_id",
        lambda db, uid: SimpleNamespace(id=uid),  # noqa: ARG005
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.build_session.get_build_session",
        lambda sid, uid, db: session,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.sandbox.get_sandbox_by_user_id",
        lambda db, uid: sandbox,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "onyx.server.features.build.skills_subset.visible_skill_slugs",
        lambda db, user: visible,  # noqa: ARG005
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.SessionManager", _Mgr
    )
    import contextlib

    @contextlib.contextmanager
    def _fake_db():
        yield SimpleNamespace(commit=lambda: None)

    monkeypatch.setattr(
        "onyx.db.engine.sql_engine.get_session_with_current_tenant",
        _fake_db,
    )
    return calls


def test_request_skill_links_and_directs_reading(
    monkeypatch: pytest.MonkeyPatch,
    fake_cache: _FakeCache,  # noqa: ARG001
) -> None:
    session = SimpleNamespace(id=uuid4(), skill_slugs=["docx", "pptx"], user_id=uuid4())
    calls = _patch_lookup(
        monkeypatch,
        visible={"docx", "pptx", "caishui-skill"},
        session=session,
        sandbox=SimpleNamespace(id=uuid4()),
    )
    result = RequestSkillTool().execute(
        ToolInvocation(
            tool="request_skill",
            arguments={"slug": "caishui-skill", "reason": "tax filing task"},
            session_id=str(session.id),
        ),
        CTX,
    )
    assert calls == ["caishui-skill"]
    text = result.text()
    assert "linked" in text
    assert ".opencode/skills/caishui-skill/SKILL.md" in text
    assert "next turn" in text
    # Dirty flag set, and consumed exactly once.
    assert take_skill_catalog_dirty(session.id) is True
    assert take_skill_catalog_dirty(session.id) is False


def test_request_skill_rejects_invisible_slug(
    monkeypatch: pytest.MonkeyPatch,
    fake_cache: _FakeCache,  # noqa: ARG001
) -> None:
    session = SimpleNamespace(id=uuid4(), skill_slugs=["docx"], user_id=uuid4())
    calls = _patch_lookup(
        monkeypatch,
        visible={"docx"},
        session=session,
        sandbox=SimpleNamespace(id=uuid4()),
    )
    result = RequestSkillTool().execute(
        ToolInvocation(
            tool="request_skill",
            arguments={"slug": "secret-skill"},
            session_id=str(session.id),
        ),
        CTX,
    )
    assert calls == []  # never linked
    assert "not in your visible skill catalog" in result.text()
    assert take_skill_catalog_dirty(session.id) is False


def test_request_skill_already_linked_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
    fake_cache: _FakeCache,  # noqa: ARG001
) -> None:
    session = SimpleNamespace(
        id=uuid4(), skill_slugs=["docx", "caishui-skill"], user_id=uuid4()
    )
    calls = _patch_lookup(
        monkeypatch,
        visible={"docx", "caishui-skill"},
        session=session,
        sandbox=SimpleNamespace(id=uuid4()),
    )
    result = RequestSkillTool().execute(
        ToolInvocation(
            tool="request_skill",
            arguments={"slug": "caishui-skill"},
            session_id=str(session.id),
        ),
        CTX,
    )
    assert calls == []
    assert "already linked" in result.text()


def test_request_skill_relink_failure_still_points_at_file(
    monkeypatch: pytest.MonkeyPatch,
    fake_cache: _FakeCache,  # noqa: ARG001
) -> None:
    session = SimpleNamespace(id=uuid4(), skill_slugs=["docx"], user_id=uuid4())
    _patch_lookup(
        monkeypatch,
        visible={"docx", "pptx"},
        session=session,
        sandbox=SimpleNamespace(id=uuid4()),
        extend_result=False,
    )
    result = RequestSkillTool().execute(
        ToolInvocation(
            tool="request_skill",
            arguments={"slug": "pptx"},
            session_id=str(session.id),
        ),
        CTX,
    )
    # No dirty flag: nothing changed.
    assert take_skill_catalog_dirty(session.id) is False
    assert ".opencode/skills/pptx/SKILL.md" in result.text()


def test_request_skill_requires_session_context() -> None:
    result = RequestSkillTool().execute(
        ToolInvocation(tool="request_skill", arguments={"slug": "x"}),
        CTX,
    )
    assert "unavailable" in result.text()


def test_registry_includes_request_skill() -> None:
    from onyx.server.features.build.tools.registry import PlatformToolRegistry

    assert "request_skill" in PlatformToolRegistry.build(
        __import__(
            "onyx.server.features.build.tools.registry", fromlist=["ToolBindings"]
        ).ToolBindings()
    )
