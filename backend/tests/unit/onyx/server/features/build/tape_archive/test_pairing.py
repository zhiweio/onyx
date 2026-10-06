"""Read-side call→result pairing over tape events (dsh semantics)."""

from typing import Any

from onyx.server.features.build.tape_archive.pairing import analyze_pairings


class _Event:
    def __init__(
        self,
        source_id: int,
        kind: str,
        subtype: str,
        payload: dict[str, Any],
    ) -> None:
        self.source_id = source_id
        self.kind = kind
        self.subtype = subtype
        self.payload = payload


def _opencode_call(sid: int, call_id: str, status: str | None = None) -> _Event:
    part: dict[str, Any] = {"toolCallId": call_id, "tool": "bash"}
    if status is not None:
        part["status"] = status
    return _Event(sid, "harness_message", "message.part.updated", {"part": part})


def _turn_event(sid: int, subtype: str, turn: int, reason: str | None = None) -> _Event:
    payload: dict[str, Any] = {"turn_index": turn}
    if reason is not None:
        payload["reason"] = reason
    return _Event(sid, "context_event", subtype, payload)


def test_opencode_paired_call() -> None:
    state = analyze_pairings(
        [
            _turn_event(1, "turn/start", 0),
            _opencode_call(2, "call-1"),
            _opencode_call(3, "call-1", "completed"),
            _turn_event(4, "turn/end", 0, reason="completed"),
        ]
    )
    pair = state.pairs["call-1"]
    assert pair.start_source_id == 2
    assert pair.end_source_id == 3
    assert not pair.interrupted
    assert "call:call-1" in state.annotations_for(2)
    assert "result:call-1" in state.annotations_for(3)


def test_open_turn_marks_interrupted() -> None:
    state = analyze_pairings(
        [
            _turn_event(1, "turn/start", 0),
            _opencode_call(2, "call-1"),
            # No turn/end: the runner died mid-turn (dsh interrupted).
        ]
    )
    pair = state.pairs["call-1"]
    assert pair.end_source_id is None
    assert pair.interrupted
    assert "interrupted" in state.annotations_for(2)
    assert 1 in state.open_turn_starts


def test_aborted_turn_marks_interrupted() -> None:
    state = analyze_pairings(
        [
            _turn_event(1, "turn/start", 0),
            _opencode_call(2, "call-1"),
            _turn_event(3, "turn/end", 0, reason="aborted"),
        ]
    )
    assert state.pairs["call-1"].interrupted


def test_completed_turn_without_result_not_interrupted() -> None:
    state = analyze_pairings(
        [
            _turn_event(1, "turn/start", 0),
            _opencode_call(2, "call-1"),
            _turn_event(3, "turn/end", 0, reason="completed"),
        ]
    )
    # Completed turn: the call simply produced no terminal part on tape.
    assert not state.pairs["call-1"].interrupted


def test_codex_item_pairing() -> None:
    state = analyze_pairings(
        [
            _turn_event(1, "turn/start", 0),
            _Event(
                2,
                "harness_message",
                "codex:item/completed",
                {"item": {"type": "tool_call", "id": "tc-1", "tool": "shell"}},
            ),
            _turn_event(3, "turn/end", 0, reason="completed"),
        ]
    )
    pair = state.pairs["tc-1"]
    assert pair.runtime == "codex"
    assert pair.start_source_id == 2
    assert pair.end_source_id == 2
    assert pair.tool_name == "shell"
