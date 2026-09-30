"""The tool-history fold used when a chat turn enters extension cycles."""

from __future__ import annotations

from onyx.chat.llm_loop import _FOLD_KEEP_RECENT_TOOL_RESPONSES, _fold_tool_history
from onyx.chat.models import ChatMessageSimple
from onyx.configs.constants import MessageType


def _tool_response(call_id: str, text: str) -> ChatMessageSimple:
    return ChatMessageSimple(
        message=text,
        token_count=len(text),
        message_type=MessageType.TOOL_CALL_RESPONSE,
        tool_call_id=call_id,
        image_files=None,
    )


def _len_counter(text: str) -> int:
    return len(text)


def test_fold_truncates_old_responses_and_keeps_recent_verbatim() -> None:
    total = _FOLD_KEEP_RECENT_TOOL_RESPONSES + 3
    history: list[ChatMessageSimple] = []
    for i in range(total):
        history.append(
            ChatMessageSimple(
                message="question",
                token_count=8,
                message_type=MessageType.USER,
                image_files=None,
            )
        )
        history.append(_tool_response(f"call-{i}", f"HEAD-{i} " + "x" * 500))
    original_recent = history[-2].message

    folded = _fold_tool_history(history, token_counter=_len_counter)

    assert folded == 3
    # The oldest response is now a stub naming its tool call id and keeping
    # the head of the result.
    oldest = history[1]
    assert oldest.tool_call_id == "call-0"
    assert "folded" in oldest.message
    assert "HEAD-0" in oldest.message
    assert oldest.token_count == len(oldest.message)
    # The most recent responses stay verbatim.
    assert history[-2].message == original_recent
    assert history[-2].token_count == len(original_recent)


def test_fold_is_noop_below_threshold() -> None:
    history = [_tool_response(f"call-{i}", "short") for i in range(3)]
    before = [msg.message for msg in history]

    assert _fold_tool_history(history, token_counter=_len_counter) == 0
    assert [msg.message for msg in history] == before


def test_fold_is_idempotent() -> None:
    history = [_tool_response(f"call-{i}", "x" * 500) for i in range(10)]
    first = _fold_tool_history(history, token_counter=_len_counter)
    second = _fold_tool_history(history, token_counter=_len_counter)

    assert first > 0
    assert second == 0
