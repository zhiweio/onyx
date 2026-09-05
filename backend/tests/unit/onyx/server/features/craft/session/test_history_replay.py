from __future__ import annotations

from types import SimpleNamespace

from onyx.configs.constants import MessageType
from onyx.server.features.build.session.history_replay import (
    REPLAY_CHAR_BUDGET,
    apply_replay_preamble,
    format_replay_preamble,
    message_after_session_replace,
)


def _msg(message_type: MessageType, meta_type: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type=message_type,
        message_metadata={
            "type": meta_type,
            "content": {"type": "text", "text": text},
        },
    )


def test_format_replay_preamble_skips_current_user_and_non_text() -> None:
    messages = [
        _msg(MessageType.USER, "user_message", "first question"),
        _msg(MessageType.ASSISTANT, "agent_message", "first answer"),
        _msg(MessageType.ASSISTANT, "agent_thought", "hidden thought"),
        _msg(MessageType.USER, "user_message", "follow up"),
    ]

    preamble = format_replay_preamble(messages, skip_last_user_text="follow up")

    assert preamble is not None
    assert "User: first question" in preamble
    assert "Assistant: first answer" in preamble
    assert "follow up" not in preamble
    assert "hidden thought" not in preamble
    assert "sandbox restore" in preamble


def test_format_replay_preamble_keeps_newest_within_budget() -> None:
    old = "A" * (REPLAY_CHAR_BUDGET + 50)
    messages = [
        _msg(MessageType.USER, "user_message", old),
        _msg(MessageType.ASSISTANT, "agent_message", "recent answer"),
    ]

    preamble = format_replay_preamble(messages)

    assert preamble is not None
    assert "recent answer" in preamble
    assert len(preamble) <= REPLAY_CHAR_BUDGET + 200


def test_apply_replay_preamble_prefixes_current_request() -> None:
    assert apply_replay_preamble("next", None) == "next"
    assert "Current request:\nnext" in apply_replay_preamble("next", "HISTORY")


def test_message_after_session_replace_only_when_id_changes() -> None:
    called = {"n": 0}

    def preamble() -> str | None:
        called["n"] += 1
        return "HISTORY"

    same = message_after_session_replace(
        "hi",
        previous_session_id="ses_1",
        resolved_session_id="ses_1",
        replacement_preamble=preamble,
    )
    assert same == "hi"
    assert called["n"] == 0

    first_mint = message_after_session_replace(
        "hi",
        previous_session_id=None,
        resolved_session_id="ses_new",
        replacement_preamble=preamble,
    )
    assert first_mint == "hi"
    assert called["n"] == 0

    replaced = message_after_session_replace(
        "hi",
        previous_session_id="ses_old",
        resolved_session_id="ses_new",
        replacement_preamble=preamble,
    )
    assert "HISTORY" in replaced
    assert "hi" in replaced
    assert called["n"] == 1
