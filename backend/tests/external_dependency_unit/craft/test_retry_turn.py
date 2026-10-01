"""Retry-turn endpoint semantics (capability-driven rewind vs resend).

The endpoint is exercised directly (function-level, matching the craft API
test convention) with the lock/turn-runner machinery monkeypatched away and
a stub sandbox manager whose rewind behavior is configured per test:

- rewind success -> the old turn's rows are deleted and the retried prompt
  runs as a clean new turn;
- rewind failure / capability absent -> history is kept and the new user
  message carries ``retry_of`` pointing at the original;
- ``content`` edits the original user message's persisted text on the
  no-rewind path.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from sqlalchemy.orm import Session

from onyx.db.enums import SandboxStatus
from onyx.configs.constants import MessageType
from onyx.db.models import BuildMessage, BuildSession, Sandbox, User
from onyx.server.features.build.db.build_session import get_session_messages
from onyx.server.features.build.session import messages as messages_module
from onyx.server.features.build.session.messages import retry_turn
from onyx.server.features.build.session.models import RetryTurnRequest
from tests.common.craft.stubs import StubSandboxManager


class _FakeLock:
    def release(self) -> None:
        pass


class _FakeTurn:
    turn_id = "turn_retry_test"
    session_id: str | None = None
    turn_index = 99
    status = "RUNNING"


@pytest.fixture()
def retry_machinery(monkeypatch: pytest.MonkeyPatch) -> StubSandboxManager:
    """Strip the cache/runner plumbing; keep DB + sandbox-manager real calls."""
    monkeypatch.setattr(messages_module, "acquire_active_turn_lock", lambda *a, **k: _FakeLock())
    monkeypatch.setattr(messages_module, "get_active_turn", lambda *a, **k: None)
    monkeypatch.setattr(
        messages_module,
        "create_interactive_turn",
        lambda *a, **k: _FakeTurn(),
    )
    monkeypatch.setattr(
        messages_module, "start_interactive_turn_runner", lambda *a, **k: None
    )
    monkeypatch.setattr(messages_module, "check_token_rate_limits", lambda *a, **k: None)
    monkeypatch.setattr(
        messages_module, "session_runtime_stale", lambda *a, **k: False
    )
    monkeypatch.setattr(
        messages_module.SessionManager, "reload_session_skills", lambda *a, **k: None
    )
    # The endpoint only uses the manager for the (stubbed) skills reload;
    # constructing the real one would reach for Kubernetes config.
    monkeypatch.setattr(
        messages_module.SessionManager, "__init__", lambda self, *a, **k: None
    )

    stub = StubSandboxManager()
    monkeypatch.setattr(messages_module, "get_sandbox_manager", lambda: stub)
    return stub


def _seed_turn(
    db_session: Session,
    build_session: BuildSession,
) -> BuildMessage:
    from onyx.server.features.build.db.build_session import create_message

    user_message = create_message(
        session_id=build_session.id,
        message_type=MessageType.USER,
        turn_index=0,
        message_metadata={
            "type": "user_message",
            "content": {"type": "text", "text": "build a landing page"},
        },
        db_session=db_session,
    )
    create_message(
        session_id=build_session.id,
        message_type=MessageType.ASSISTANT,
        turn_index=0,
        message_metadata={
            "type": "agent_message",
            "content": {"type": "text", "text": "here you go"},
        },
        db_session=db_session,
    )
    db_session.commit()
    return user_message


def _attach_running_sandbox(
    db_session: Session,
    test_user: User,
    sandbox: Callable[..., Sandbox],
) -> None:
    sandbox(user=test_user, status=SandboxStatus.RUNNING)
    db_session.commit()


def test_retry_with_rewind_deletes_old_turn_and_reruns(
    db_session: Session,
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    sandbox: Callable[..., Sandbox],
    retry_machinery: StubSandboxManager,
) -> None:
    build_session = build_session_with_user(user=test_user)
    original = _seed_turn(db_session, build_session)
    _attach_running_sandbox(db_session, test_user, sandbox)
    build_session.opencode_session_id = "ses_retry_1"
    db_session.commit()

    # Rewind-capable runtime: the harness rewind succeeds.
    monkeypatch_list = {
        "list_opencode_messages": lambda *a, **k: [
            {"id": "msg_1", "role": "user"},
            {"id": "msg_2", "role": "assistant"},
        ],
        "rewind_opencode_session": lambda *a, **k: True,
    }
    for name, impl in monkeypatch_list.items():
        setattr(retry_machinery, name, impl)

    response = retry_turn(
        build_session.id,
        RetryTurnRequest(),
        user=test_user,
        db_session=db_session,
    )
    assert response.turn_id == "turn_retry_test"

    remaining = get_session_messages(build_session.id, db_session)
    # Old turn deleted; only the fresh retried user message remains.
    assert len(remaining) == 1
    assert remaining[0].type == "user"
    metadata = remaining[0].message_metadata
    assert metadata["content"]["text"] == "build a landing page"
    assert "retry_of" not in metadata
    assert original.id != remaining[0].id


def test_retry_without_rewind_keeps_history_and_annotates(
    db_session: Session,
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    sandbox: Callable[..., Sandbox],
    retry_machinery: StubSandboxManager,
) -> None:
    build_session = build_session_with_user(user=test_user)
    original = _seed_turn(db_session, build_session)
    _attach_running_sandbox(db_session, test_user, sandbox)
    build_session.opencode_session_id = "ses_retry_2"
    db_session.commit()

    # Runtime without TURN_REWIND: the rewind reports False.
    retry_machinery.rewind_opencode_session = lambda *a, **k: False

    retry_turn(
        build_session.id,
        RetryTurnRequest(),
        user=test_user,
        db_session=db_session,
    )

    remaining = get_session_messages(build_session.id, db_session)
    # History kept: original user + assistant + the annotated retry.
    assert len(remaining) == 3
    retried = [m for m in remaining if m.message_metadata.get("retry_of")]
    assert len(retried) == 1
    assert retried[0].message_metadata["retry_of"] == str(original.id)


def test_retry_with_content_edits_original_when_not_rewound(
    db_session: Session,
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    sandbox: Callable[..., Sandbox],
    retry_machinery: StubSandboxManager,
) -> None:
    build_session = build_session_with_user(user=test_user)
    original = _seed_turn(db_session, build_session)
    _attach_running_sandbox(db_session, test_user, sandbox)
    build_session.opencode_session_id = "ses_retry_3"
    db_session.commit()

    retry_machinery.rewind_opencode_session = lambda *a, **k: False

    retry_turn(
        build_session.id,
        RetryTurnRequest(content="build a landing page AND a pricing section"),
        user=test_user,
        db_session=db_session,
    )

    db_session.refresh(original)
    assert original.message_metadata["content"]["text"] == (
        "build a landing page AND a pricing section"
    )
    retried = [
        m
        for m in get_session_messages(build_session.id, db_session)
        if m.message_metadata.get("retry_of")
    ]
    assert retried[0].message_metadata["content"]["text"] == (
        "build a landing page AND a pricing section"
    )


def test_retry_without_any_turn_is_bad_request(
    db_session: Session,
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    retry_machinery: StubSandboxManager,
) -> None:
    from onyx.error_handling.exceptions import OnyxError

    build_session = build_session_with_user(user=test_user)
    with pytest.raises(OnyxError):
        retry_turn(
            build_session.id,
            RetryTurnRequest(),
            user=test_user,
            db_session=db_session,
        )
