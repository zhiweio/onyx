"""Replay translation: tape events → live wire packets (dsh same-fold rule)."""

from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import onyx.server.features.build.tape_archive.replay as replay_module
from onyx.server.features.build.tape_archive.replay import build_replay_packets


def _event(
    source_id: int,
    kind: str,
    subtype: str,
    payload: dict[str, Any],
    runtime: str = "codex",
    turn_index: int | None = 0,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    return {
        "source_id": source_id,
        "turn_index": turn_index,
        "kind": kind,
        "subtype": subtype,
        "runtime": runtime,
        "payload": payload,
        "created_at": datetime.now(timezone.utc),
    }


def _patch_events(
    monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(
        replay_module,
        "merged_tape_events",
        lambda _db, _sid, **_: events,
    )


def test_codex_delta_accumulation_and_commentary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        _event(1, "context_event", "turn/start", {"turn_index": 0}),
        _event(
            2,
            "harness_message",
            "codex:item/agentMessage/delta",
            {"itemId": "a", "delta": "Hello "},
        ),
        _event(
            3,
            "harness_message",
            "codex:item/agentMessage/delta",
            {"itemId": "a", "delta": "world"},
        ),
        _event(
            4, "context_event", "turn/end", {"turn_index": 0, "reason": "completed"}
        ),
    ]
    _patch_events(monkeypatch, events)
    page = build_replay_packets(cast(Session, None), uuid4())
    packets = [item for item in page.items if item.type == "packet"]
    wire = [p.packet or {} for p in packets]
    assert [w.get("sessionUpdate") for w in wire] == [
        "agent_message_chunk",
        "agent_message_chunk",
    ]
    contents = [w.get("content") or {} for w in wire]
    assert [c.get("text") for c in contents] == ["Hello ", "world"]
    markers = [item for item in page.items if item.type == "marker"]
    assert [m.marker for m in markers] == ["turn_start", "turn_end"]
    assert markers[1].reason == "completed"
    assert page.skipped == 0


def test_codex_tool_call_translates(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [
        _event(
            1,
            "harness_message",
            "codex:item/completed",
            {
                "item": {
                    "type": "tool_call",
                    "id": "tc-1",
                    "tool": "shell",
                    "input": {"command": ["ls"]},
                }
            },
        ),
    ]
    _patch_events(monkeypatch, events)
    page = build_replay_packets(cast(Session, None), uuid4())
    packets = [item for item in page.items if item.type == "packet"]
    assert packets
    types = {(p.packet or {}).get("sessionUpdate") for p in packets}
    assert "tool_call" in types


def test_opencode_part_stream_and_session_keying(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "sess-1"
    events = [
        _event(
            1,
            "harness_message",
            "message.updated",
            {
                "type": "message.updated",
                "properties": {
                    "sessionID": session_id,
                    "info": {"id": "m1", "role": "assistant"},
                },
            },
            runtime="opencode",
        ),
        _event(
            2,
            "harness_message",
            "message.part.updated",
            {
                "type": "message.part.updated",
                "properties": {
                    "sessionID": session_id,
                    "part": {
                        "id": "p1",
                        "type": "text",
                        "messageID": "m1",
                        "text": "Hi there",
                    },
                },
            },
            runtime="opencode",
        ),
    ]
    _patch_events(monkeypatch, events)
    page = build_replay_packets(cast(Session, None), uuid4())
    packets = [item for item in page.items if item.type == "packet"]
    # fetch callbacks are None: the recorded part stream still rebuilds text.
    assert any(
        (p.packet or {}).get("sessionUpdate") == "agent_message_chunk" for p in packets
    )


def test_dirty_event_skips_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom(dict):
        def get(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("dirty row")

    events = [
        Boom(),  # raises during translation
        _event(2, "context_event", "turn/start", {"turn_index": 0}),
    ]
    _patch_events(monkeypatch, events)
    page = build_replay_packets(cast(Session, None), uuid4())
    assert page.skipped == 1
    assert any(item.marker == "turn_start" for item in page.items)


def test_turn_filter_and_unknown_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        _event(1, "context_event", "turn/start", {"turn_index": 0}, turn_index=0),
        _event(2, "context_event", "turn/start", {"turn_index": 1}, turn_index=1),
        _event(
            3,
            "harness_message",
            "message.part.updated",
            {},
            runtime="eval",
            turn_index=1,
        ),
        _event(4, "context_event", "turn/end", {"turn_index": 1}, turn_index=1),
    ]
    _patch_events(monkeypatch, events)
    page = build_replay_packets(cast(Session, None), uuid4(), turn_index=1)
    turns = {item.turn_index for item in page.items}
    assert turns == {1}
    assert page.skipped == 1  # eval runtime is not replayable


def test_cursor_pagination_next_source_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        _event(1, "context_event", "turn/start", {"turn_index": 0}),
        _event(2, "context_event", "turn/end", {"turn_index": 0}),
        _event(3, "context_event", "turn/start", {"turn_index": 1}),
    ]
    captured: dict[str, Any] = {}

    def fake_merged(
        _db: Any, _sid: Any, *, after_source_id: Any = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        captured["after"] = after_source_id
        captured["limit"] = limit
        return events[:limit]

    monkeypatch.setattr(replay_module, "merged_tape_events", fake_merged)
    page = build_replay_packets(cast(Session, None), uuid4(), limit=2)
    assert captured["limit"] == 2
    # Full page read → cursor continues after the last event read.
    assert page.next_source_id == 2
