"""Long-term memory isolation, filters, and recall ranking."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from onyx.db.enums import ChatMemoryMode
from onyx.db.models import User
from onyx.memory.filters import reject_reason
from onyx.memory.long_term import (
    MemoryFact,
    maybe_craft_recall_prompt,
    recall,
    upsert_facts,
)
from onyx.server.features.build.jobs.assembler import assemble_brief
from onyx.server.features.build.jobs.channels import empty_state
from onyx.server.features.build.jobs.graph import compile_graph
from tests.external_dependency_unit.conftest import create_test_user


def _vector_for(text_value: str, dims: int = 8) -> list[float]:
    seed = sum(ord(ch) for ch in text_value.lower())
    vec = [((seed * (i + 3)) % 97) / 97.0 for i in range(dims)]
    if "btk" in text_value.lower() or "dlbcl" in text_value.lower():
        vec[0] = 0.99
    if "favorite color" in text_value.lower():
        vec[1] = 0.99
    return vec


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


def _embed_side_effect(
    _db_session: Session, texts: list[str], *, query: bool
) -> list[list[float]]:
    del query
    return [_vector_for(item) for item in texts]


def test_reject_secret_and_short_text() -> None:
    assert reject_reason("sk-abc1234567890secret") == "secret"
    assert reject_reason("hi") == "too_short"
    assert reject_reason("User prefers dark mode in Craft") is None


@pytest.mark.usefixtures("pgvector_ready")
def test_recall_is_user_isolated(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user_a = create_test_user(db_session, email_prefix="ltm_a")
    user_b = create_test_user(db_session, email_prefix="ltm_b")
    with patch(
        "onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect
    ), patch(
        "onyx.memory.long_term._embedding_model",
        return_value=(object(), "test-model", 8),
    ):
        upsert_facts(
            db_session,
            user_a.id,
            [MemoryFact(text="User prefers BTK inhibitor notes in Craft")],
            source="extract",
            source_surface="craft",
        )
        upsert_facts(
            db_session,
            user_b.id,
            [MemoryFact(text="User prefers favorite color green")],
            source="extract",
            source_surface="chat",
        )
        db_session.commit()
        recalled_a = recall(db_session, user_a.id, "BTK inhibitor DLBCL")
        recalled_b = recall(db_session, user_b.id, "favorite color")

    assert any("BTK" in item.text for item in recalled_a)
    assert all("favorite color" not in item.text for item in recalled_a)
    assert any("favorite color" in item.text for item in recalled_b)
    assert all("BTK" not in item.text for item in recalled_b)


@pytest.mark.usefixtures("pgvector_ready")
def test_hash_dedupe_and_secret_drop(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, email_prefix="ltm_dedupe")
    with patch(
        "onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect
    ), patch(
        "onyx.memory.long_term._embedding_model",
        return_value=(object(), "test-model", 8),
    ):
        first = upsert_facts(
            db_session,
            user.id,
            [MemoryFact(text="User wants 1L DLBCL expansion reviewed")],
            source="extract",
            source_surface="craft",
        )
        second = upsert_facts(
            db_session,
            user.id,
            [MemoryFact(text="User wants 1L DLBCL expansion reviewed")],
            source="extract",
            source_surface="craft",
        )
        secret = upsert_facts(
            db_session,
            user.id,
            [MemoryFact(text="api_key=supersecretvalue")],
            source="extract",
            source_surface="craft",
        )
        db_session.commit()
    assert first == second
    assert secret == []


@pytest.mark.usefixtures("pgvector_ready")
def test_craft_toggle_off_skips_recall_prompt(
    db_session: Session, test_user: User
) -> None:
    from onyx.db.models import BuildSession
    from onyx.db.enums import BuildSessionStatus, SessionOrigin

    test_user.craft_use_long_term_memory = False
    session = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="ltm",
        status=BuildSessionStatus.ACTIVE,
        origin=SessionOrigin.INTERACTIVE,
    )
    db_session.add(session)
    db_session.commit()
    prompt = maybe_craft_recall_prompt(db_session, session.id, "hello from user")
    assert prompt == "hello from user"


@pytest.mark.usefixtures("pgvector_ready")
def test_chat_long_term_can_read_craft_row(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
) -> None:
    user = create_test_user(db_session, email_prefix="ltm_bridge")
    user.chat_memory_mode = ChatMemoryMode.LONG_TERM
    with patch(
        "onyx.memory.long_term.embed_texts", side_effect=_embed_side_effect
    ), patch(
        "onyx.memory.long_term._embedding_model",
        return_value=(object(), "test-model", 8),
    ):
        upsert_facts(
            db_session,
            user.id,
            [MemoryFact(text="User is evaluating HMPL-760 1L DLBCL expansion")],
            source="extract",
            source_surface="craft",
        )
        db_session.commit()
        recalled = recall(db_session, user.id, "HMPL-760 DLBCL")
    assert any("HMPL-760" in item.text for item in recalled)


def test_assemble_brief_includes_recalled_memories() -> None:
    node = compile_graph().get("plan")
    assert node is not None
    brief = assemble_brief(
        node=node,
        state=empty_state(),
        job_name="biomed",
        domain="biomed",
        recalled_memories=["User prefers conservative go or no-go framing"],
    )
    assert "Recalled memories" in brief
    assert "conservative go or no-go" in brief
