"""F2-A: subscribe_to_existing_session_events must replay the newest turn's
persisted packets before the live stream (mid-turn attachers would otherwise
miss tool events that fired before their 5s poll discovered the turn), and
drop live duplicates of replayed terminal tool events."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from onyx.configs.constants import MessageType
from onyx.db.enums import SandboxStatus
from onyx.server.features.build.session import manager as session_manager


def _assistant_row(turn_index: int, metadata: dict, seq: int) -> MagicMock:
    row = MagicMock()
    row.type = MessageType.ASSISTANT
    row.turn_index = turn_index
    row.message_metadata = metadata
    # created_at used only for ordering in the query; replay preserves it.
    row.created_at = seq
    return row


def test_load_replayable_events_only_newest_turn_assistant_rows() -> None:
    mgr = MagicMock(spec=session_manager.SessionManager)
    mgr._db_session = MagicMock()
    older_tool = _assistant_row(
        1, {"type": "tool_call_progress", "toolCallId": "t1"}, 0
    )
    text_packet = _assistant_row(2, {"type": "message", "text": "hi"}, 1)
    tool_row = _assistant_row(
        2,
        {
            "type": "tool_call_progress",
            "toolCallId": "t2",
            "status": "completed",
        },
        2,
    )
    user_row = MagicMock()
    user_row.type = MessageType.USER
    # Query result order: turn_index DESC, created_at ASC (DB does the sort).
    mgr._db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        text_packet,
        tool_row,
        older_tool,
        user_row,
    ]

    replay = session_manager.SessionManager._load_replayable_events(mgr, uuid4())
    # Only the newest turn (2), assistant rows, chronological.
    assert [p["type"] for p in replay] == ["message", "tool_call_progress"]
    assert replay[0]["text"] == "hi"
    assert replay[1]["toolCallId"] == "t2"
    # parent/child attribution defaults so subagent routing survives replay.
    assert all(p["sessionId"] is None for p in replay)


def test_subscribe_yields_replay_then_dedupes_live_terminal_tool_event() -> None:
    mgr = MagicMock(spec=session_manager.SessionManager)
    mgr._db_session = MagicMock()
    mgr._sandbox_manager = MagicMock()
    mgr._load_replayable_events = MagicMock(
        return_value=[
            {
                "type": "tool_call_progress",
                "toolCallId": "tc-9",
                "status": "completed",
            }
        ]
    )
    session = MagicMock()
    session.opencode_session_id = "ses_1"
    mgr._db_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        _assistant_row(
            3,
            {
                "type": "tool_call_progress",
                "toolCallId": "tc-9",
                "status": "completed",
            },
            0,
        )
    ]
    get_session = patch.object(
        session_manager, "get_build_session", return_value=session
    )
    get_sandbox = patch.object(session_manager, "get_sandbox_by_user_id")
    get_sandbox.start().return_value = MagicMock(status=SandboxStatus.RUNNING)

    live_tool_event = MagicMock()
    live_tool_event.model_dump.return_value = {
        "type": "tool_call_progress",
        "toolCallId": "tc-9",
        "status": "completed",
    }
    live_text_event = MagicMock()
    live_text_event.model_dump.return_value = {"type": "text_chunk"}

    subscribe = patch.object(
        mgr._sandbox_manager,
        "subscribe_to_opencode_session",
        return_value=iter([live_tool_event, live_text_event]),
    )
    event_to_sse = patch.object(
        session_manager._streaming,
        "event_to_sse",
        side_effect=lambda e: f"LIVE:{e}",
    )

    with get_session, subscribe, event_to_sse:
        events = list(
            session_manager.SessionManager.subscribe_to_existing_session_events(
                mgr, uuid4(), uuid4(), include_approval_announces=False
            )
        )

    # First yielded frame is the replayed persisted packet as raw SSE.
    assert events[0].startswith("event: message\ndata: ")
    assert "tc-9" in events[0]
    # The live duplicate of the replayed terminal tool event is dropped; the
    # live text event passes through (exactly one LIVE frame, for the text).
    live_frames = [e for e in events[1:] if e.startswith("LIVE:")]
    assert len(events) == 2
    assert len(live_frames) == 1
