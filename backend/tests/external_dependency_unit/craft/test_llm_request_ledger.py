"""External-dependency tests for the craft per-request LLM ledger.

Real Postgres: the upsert's (session_id, opencode_message_id) conflict path
and the newly-inserted flag only prove themselves against the actual
unique constraint.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from onyx.db.craft_llm_request import (
    session_llm_usage_totals,
    upsert_craft_llm_request,
)
from onyx.db.models import BuildSession


def _make_session(db_session: Session, user_id) -> BuildSession:
    row = BuildSession(user_id=user_id, name="ledger-test")
    db_session.add(row)
    db_session.flush()
    return row


def test_upsert_is_idempotent_per_message(db_session: Session) -> None:
    from tests.external_dependency_unit.craft.db_helpers import make_user

    user = make_user(db_session)
    session = _make_session(db_session, user.id)

    created_first = upsert_craft_llm_request(
        db_session,
        session_id=session.id,
        turn_index=0,
        opencode_message_id="msg_1",
        provider="openai",
        model="gpt-x",
        input_tokens=100,
        output_tokens=20,
        reasoning_tokens=5,
        cache_read_tokens=30,
        cache_write_tokens=10,
        cost=0.01,
    )
    assert created_first is True

    # The harness re-reports the same message with updated numbers.
    created_second = upsert_craft_llm_request(
        db_session,
        session_id=session.id,
        turn_index=0,
        opencode_message_id="msg_1",
        provider="openai",
        model="gpt-x",
        input_tokens=120,
        output_tokens=25,
        reasoning_tokens=5,
        cache_read_tokens=30,
        cache_write_tokens=10,
        cost=0.012,
    )
    assert created_second is False

    db_session.commit()
    totals = session_llm_usage_totals(db_session, [session.id])
    row = totals[str(session.id)]
    assert row["input_tokens"] == 120.0
    assert row["output_tokens"] == 25.0
    assert row["cost"] == 0.012


def test_totals_sum_across_sessions_and_messages(db_session: Session) -> None:
    from tests.external_dependency_unit.craft.db_helpers import make_user

    user = make_user(db_session)
    first = _make_session(db_session, user.id)
    second = _make_session(db_session, user.id)
    for index, session in enumerate((first, second)):
        for message_index in range(3):
            upsert_craft_llm_request(
                db_session,
                session_id=session.id,
                turn_index=0,
                opencode_message_id=f"msg_{index}_{message_index}",
                provider="openai",
                model="gpt-x",
                input_tokens=10,
                output_tokens=2,
                reasoning_tokens=1,
                cache_read_tokens=3,
                cache_write_tokens=1,
                cost=0.001,
            )
    db_session.commit()
    totals = session_llm_usage_totals(db_session, [first.id, second.id])
    for session in (first, second):
        row = totals[str(session.id)]
        assert row["input_tokens"] == 30.0
        assert row["output_tokens"] == 6.0
    assert session_llm_usage_totals(db_session, []) == {}
