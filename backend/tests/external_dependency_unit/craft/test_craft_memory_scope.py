"""P5 memory scope semantics + memory tool RBAC (external-dependency).

Covers the hard read scope (project rows shared with the team, private
rows never leaking), the project memory switch, and the
memory_write / memory_search platform tools against the real store.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from onyx.db.enums import SessionOrigin
from onyx.db.models import BuildSession, CraftProject, User, User__UserGroup, UserGroup
from onyx.memory.long_term import (
    MemoryFact,
    maybe_craft_recall_prompt,
    recall,
    session_memory_scope,
    upsert_facts,
)
from onyx.server.features.build.tools.base import (
    ToolContext,
    ToolInvocation,
    ToolResult,
)
from onyx.server.features.build.tools.implementations import (
    memory_search_tool,
    memory_write_tool,
)
from tests.external_dependency_unit.conftest import create_test_user


def _embed_side_effect(
    _db_session: Session,
    texts: list[str],
    *,
    query: bool,  # noqa: ARG001
) -> list[list[float]]:
    # Deterministic, distinct-enough vectors keyed by content.
    out = []
    for item in texts:
        seed = sum(ord(ch) for ch in item.lower())
        out.append([((seed * (i + 3)) % 97) / 97.0 for i in range(8)])
    return out


@pytest.fixture
def pgvector_ready(db_session: Session) -> Iterator[None]:
    try:
        db_session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db_session.commit()
        db_session.execute(text("SELECT '[1,2,3]'::vector"))
    except Exception as exc:
        db_session.rollback()
        pytest.skip(f"pgvector is not available: {exc}")
    yield


@pytest.fixture
def team(db_session: Session) -> dict[str, Any]:
    """owner + member sharing a group/project; outsider in nothing."""
    owner = create_test_user(db_session, email_prefix="p5_owner")
    member = create_test_user(db_session, email_prefix="p5_member")
    outsider = create_test_user(db_session, email_prefix="p5_out")
    group = UserGroup(name=f"p5-group-{uuid4().hex[:8]}")
    db_session.add(group)
    db_session.flush()
    db_session.add(User__UserGroup(user_id=owner.id, user_group_id=group.id))
    db_session.add(User__UserGroup(user_id=member.id, user_group_id=group.id))
    project = CraftProject(
        user_id=owner.id,
        name=f"p5-proj-{uuid4().hex[:6]}",
        description="",
        user_group_id=group.id,
        memory_enabled=True,
    )
    db_session.add(project)
    db_session.flush()
    db_session.commit()
    return {
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "group": group,
        "project": project,
    }


def _seed_memories(db_session: Session, team: dict[str, Any]) -> None:
    with (
        patch("onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect),
        patch(
            "onyx.memory.long_term._embedding_model",
            return_value=(object(), "test-model", 8),
        ),
    ):
        upsert_facts(
            db_session,
            team["owner"].id,
            [MemoryFact(text="Owner private fact about report layout")],
            source="agent",
            source_surface="craft",
        )
        upsert_facts(
            db_session,
            team["owner"].id,
            [MemoryFact(text="Project convention: use thirteen percent VAT notes")],
            source="agent",
            source_surface="craft",
            project_id=team["project"].id,
        )
        upsert_facts(
            db_session,
            team["member"].id,
            [MemoryFact(text="Member private fact about breakfast cereal")],
            source="agent",
            source_surface="craft",
        )
        db_session.commit()


def _session_for(
    db_session: Session, user: User, project: CraftProject | None
) -> BuildSession:
    session = BuildSession(
        user_id=user.id,
        name=f"p5-session-{uuid4().hex[:6]}",
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id if project is not None else None,
    )
    db_session.add(session)
    db_session.commit()
    return session


def _texts(result: ToolResult) -> str:
    return "\n".join(
        block.get("text", "") for block in result.content if isinstance(block, dict)
    )


@pytest.mark.usefixtures("pgvector_ready")
def test_project_scope_shares_project_rows_only(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    _seed_memories(db_session, team)
    with (
        patch("onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect),
        patch(
            "onyx.memory.long_term._embedding_model",
            return_value=(object(), "test-model", 8),
        ),
    ):
        # Owner, project scope: own private + shared project rows.
        got = recall(
            db_session,
            team["owner"].id,
            "VAT report layout",
            project_id=team["project"].id,
        )
        texts = {item.text for item in got}
        assert "Project convention: use thirteen percent VAT notes" in texts
        assert "Owner private fact about report layout" in texts
        # Member, project scope: shared project rows + their own private —
        # NOT the owner's private row.
        got = recall(
            db_session,
            team["member"].id,
            "VAT report layout",
            project_id=team["project"].id,
        )
        texts = {item.text for item in got}
        assert "Project convention: use thirteen percent VAT notes" in texts
        assert "Member private fact about breakfast cereal" in texts
        assert "Owner private fact about report layout" not in texts
        # No project scope: private rows only — project rows are hidden.
        got = recall(db_session, team["owner"].id, "VAT report layout")
        texts = {item.text for item in got}
        assert "Owner private fact about report layout" in texts
        assert "Project convention: use thirteen percent VAT notes" not in texts


@pytest.mark.usefixtures("pgvector_ready")
def test_session_scope_resolves_grants_and_switches(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    _seed_memories(db_session, team)
    project = team["project"]

    # Project memory on + member has read grant → project scope.
    member_session = _session_for(db_session, team["member"], project)
    scope = session_memory_scope(db_session, member_session)
    assert scope is not None and scope.project_id == project.id

    # Outsider (no group) → memoryless for this project even though the
    # switch is on; their own flag is off too.
    outsider_session = _session_for(db_session, team["outsider"], project)
    assert session_memory_scope(db_session, outsider_session) is None

    # Project switch off + user flag off → None even for the owner.
    project.memory_enabled = False
    db_session.commit()
    owner_session = _session_for(db_session, team["owner"], project)
    assert session_memory_scope(db_session, owner_session) is None

    # User flag on → user-only scope despite project switch off.
    team["owner"].craft_use_long_term_memory = True
    db_session.commit()
    scope = session_memory_scope(db_session, owner_session)
    assert scope is not None and scope.project_id is None
    team["owner"].craft_use_long_term_memory = False
    db_session.commit()


@pytest.mark.usefixtures("pgvector_ready")
def test_memory_write_tool_scope_permissions(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    tool = memory_write_tool()
    project = team["project"]
    owner_session = _session_for(db_session, team["owner"], project)
    member_session = _session_for(db_session, team["member"], project)

    with (
        patch("onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect),
        patch(
            "onyx.memory.long_term._embedding_model",
            return_value=(object(), "test-model", 8),
        ),
    ):
        # Owner writes a shared project memory.
        result = tool.execute(
            ToolInvocation(
                tool="memory_write",
                arguments={
                    "text": "Filing deadline is the fifteenth of each month",
                    "scope": "project",
                },
                session_id=str(owner_session.id),
                sandbox_id=None,
            ),
            ToolContext(user_id=str(team["owner"].id), tenant_id="public"),
        )
        assert "stored" in _texts(result)

        # Member cannot write shared project memory.
        result = tool.execute(
            ToolInvocation(
                tool="memory_write",
                arguments={
                    "text": "Try to widen the shared surface",
                    "scope": "project",
                },
                session_id=str(member_session.id),
                sandbox_id=None,
            ),
            ToolContext(user_id=str(team["member"].id), tenant_id="public"),
        )
        assert "write access" in _texts(result)

        # Member CAN write a private user memory.
        result = tool.execute(
            ToolInvocation(
                tool="memory_write",
                arguments={"text": "Member prefers concise summaries"},
                session_id=str(member_session.id),
                sandbox_id=None,
            ),
            ToolContext(user_id=str(team["member"].id), tenant_id="public"),
        )
        assert "stored" in _texts(result)

        # Secrets are rejected outright.
        result = tool.execute(
            ToolInvocation(
                tool="memory_write",
                arguments={"text": "sk-abc1234567890secret"},
                session_id=str(member_session.id),
                sandbox_id=None,
            ),
            ToolContext(user_id=str(team["member"].id), tenant_id="public"),
        )
        assert "rejected" in _texts(result)
        db_session.commit()


@pytest.mark.usefixtures("pgvector_ready")
def test_memory_tools_fail_closed_when_disabled(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    project = team["project"]
    project.memory_enabled = False
    db_session.commit()
    owner_session = _session_for(db_session, team["owner"], project)

    write = memory_write_tool().execute(
        ToolInvocation(
            tool="memory_write",
            arguments={"text": "Should not persist anywhere at all"},
            session_id=str(owner_session.id),
            sandbox_id=None,
        ),
        ToolContext(user_id=str(team["owner"].id), tenant_id="public"),
    )
    assert "disabled" in _texts(write)

    search = memory_search_tool().execute(
        ToolInvocation(
            tool="memory_search",
            arguments={"query": "anything"},
            session_id=str(owner_session.id),
            sandbox_id=None,
        ),
        ToolContext(user_id=str(team["owner"].id), tenant_id="public"),
    )
    assert "disabled" in _texts(search)


@pytest.mark.usefixtures("pgvector_ready")
def test_memory_search_tool_returns_attributed_hints(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    _seed_memories(db_session, team)
    member_session = _session_for(db_session, team["member"], team["project"])
    with (
        patch("onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect),
        patch(
            "onyx.memory.long_term._embedding_model",
            return_value=(object(), "test-model", 8),
        ),
    ):
        result = memory_search_tool().execute(
            ToolInvocation(
                tool="memory_search",
                arguments={"query": "VAT notes"},
                session_id=str(member_session.id),
                sandbox_id=None,
            ),
            ToolContext(user_id=str(team["member"].id), tenant_id="public"),
        )
    out = _texts(result)
    assert "untrusted" in out
    assert "project-shared" in out
    assert "thirteen percent VAT" in out
    # The owner's private row never reaches the member via search either.
    assert "Owner private fact" not in out


@pytest.mark.usefixtures("pgvector_ready")
def test_recall_prompt_uses_project_scope(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    team: dict[str, Any],
) -> None:
    _seed_memories(db_session, team)
    member_session = _session_for(db_session, team["member"], team["project"])
    with (
        patch("onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect),
        patch(
            "onyx.memory.long_term._embedding_model",
            return_value=(object(), "test-model", 8),
        ),
    ):
        prompt = maybe_craft_recall_prompt(
            db_session, member_session.id, " VAT report layout "
        )
    assert "thirteen percent VAT" in prompt
    assert "member_session" not in prompt
