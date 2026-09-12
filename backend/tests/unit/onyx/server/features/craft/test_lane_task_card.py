from uuid import uuid4

from onyx.server.features.build.jobs.lane_task import (
    LANE_TASK_JOB_KEY,
    LANE_TASK_NODE_KEY,
    activity_label_from_metadata,
    lane_task_card_metadata,
    lane_task_lookup_ids,
    lane_task_tool_id,
    lane_task_upsert_action,
    patch_open_lane_task_status,
)
from onyx.server.features.build.jobs.kernel import _emit_lane_task_card


def test_lane_task_tool_id_is_stable() -> None:
    assert lane_task_tool_id("lane:literature") == "lane-task-lane:literature"
    assert lane_task_tool_id("lane:literature") == lane_task_tool_id("lane:literature")


def test_lane_task_lookup_ids_include_legacy_status_suffix() -> None:
    ids = lane_task_lookup_ids("lane:researcher")
    assert "lane-task-lane:researcher" in ids
    assert "lane-task-lane:researcher-in_progress" in ids
    assert "lane-task-lane:researcher-2-in_progress" not in ids
    assert lane_task_lookup_ids("lane:researcher") != lane_task_lookup_ids(
        "lane:researcher-2"
    )


def test_lane_task_card_carries_specialist_session() -> None:
    specialist_id = uuid4()
    job_id = uuid4()
    metadata = lane_task_card_metadata(
        node_id="lane:literature",
        name="Literature",
        status="in_progress",
        notes_path="outputs/normalized/patents.csv",
        specialist_session_id=specialist_id,
        role="literature",
        job_id=job_id,
    )
    assert metadata[LANE_TASK_NODE_KEY] == "lane:literature"
    assert metadata[LANE_TASK_JOB_KEY] == str(job_id)
    tool = metadata["streamItems"][0]["toolCall"]
    assert tool["id"] == "lane-task-lane:literature"
    assert tool["status"] == "in_progress"
    assert tool["subagentType"] == "literature"
    assert tool["subagentSessionId"] == str(specialist_id)
    assert tool["jobId"] == str(job_id)
    assert "in_progress" not in tool["id"]


def test_lane_end_card_keeps_the_same_tool_id() -> None:
    specialist_id = uuid4()
    started = lane_task_card_metadata(
        node_id="lane:clinical",
        name="Clinical",
        status="in_progress",
        notes_path="outputs/normalized/readouts.csv",
        specialist_session_id=specialist_id,
        role="clinical",
    )
    finished = lane_task_card_metadata(
        node_id="lane:clinical",
        name="Clinical",
        status="completed",
        notes_path="outputs/normalized/readouts.csv",
        specialist_session_id=specialist_id,
        role="clinical",
    )
    assert started["streamItems"][0]["id"] == finished["streamItems"][0]["id"]
    assert finished["streamItems"][0]["toolCall"]["status"] == "completed"


def test_activity_label_prefers_latest_tool() -> None:
    label = activity_label_from_metadata(
        {
            "type": "assistant_message",
            "streamItems": [
                {
                    "type": "tool_call",
                    "toolCall": {"description": "outputs/old.md"},
                },
                {
                    "type": "tool_call",
                    "toolCall": {"description": "Writing pipeline.csv"},
                },
            ],
        }
    )
    assert label == "Writing pipeline.csv"


def test_activity_label_from_thought_packet() -> None:
    label = activity_label_from_metadata(
        {
            "type": "agent_thought",
            "content": {"text": "The NOTES.md belongs to another lane.\nMore"},
        }
    )
    assert label == "The NOTES.md belongs to another lane."


def test_upsert_starts_a_new_card_after_cancel() -> None:
    old_session = uuid4()
    new_session = uuid4()
    cancelled = lane_task_card_metadata(
        node_id="lane:researcher",
        name="Researcher",
        status="cancelled",
        notes_path="outputs/normalized/epi.md",
        specialist_session_id=old_session,
        role="researcher",
        job_id=uuid4(),
    )
    nxt = lane_task_card_metadata(
        node_id="lane:researcher",
        name="Researcher",
        status="in_progress",
        notes_path="outputs/normalized/epi.md",
        specialist_session_id=new_session,
        role="researcher",
        job_id=uuid4(),
    )
    assert lane_task_upsert_action(cancelled, nxt) == "create"
    leftover = lane_task_card_metadata(
        node_id="lane:researcher",
        name="Researcher",
        status="in_progress",
        notes_path="outputs/normalized/epi.md",
        specialist_session_id=old_session,
        role="researcher",
        job_id=uuid4(),
    )
    assert lane_task_upsert_action(leftover, nxt) == "settle_then_create"
    assert lane_task_upsert_action(nxt, nxt) == "update"


def test_emit_lane_task_card_updates_existing(monkeypatch) -> None:
    existing_id = uuid4()
    specialist_id = uuid4()
    existing_metadata = lane_task_card_metadata(
        node_id="lane:literature",
        name="Literature",
        status="in_progress",
        notes_path="outputs/a.md",
        specialist_session_id=specialist_id,
        role="literature",
    )
    updated: list[object] = []
    created: list[object] = []

    monkeypatch.setattr(
        "onyx.server.features.build.db.build_session.find_lane_task_message",
        lambda *_a, **_k: type(
            "Msg",
            (),
            {"id": existing_id, "message_metadata": existing_metadata},
        )(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.build_session.update_message",
        lambda message_id, metadata, db_session: updated.append(
            (message_id, metadata)
        ),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.build_session.create_message",
        lambda **kwargs: created.append(kwargs),
    )

    _emit_lane_task_card(
        type("Db", (), {})(),  # type: ignore[arg-type]
        session_id=uuid4(),
        node_id="lane:literature",
        name="Literature",
        status="completed",
        notes_path="outputs/a.md",
        specialist_session_id=specialist_id,
        role="literature",
    )
    assert updated
    assert not created
    _message_id, metadata = updated[0]
    assert _message_id == existing_id
    assert metadata["streamItems"][0]["toolCall"]["status"] == "completed"


def test_patch_open_lane_task_status_cancels_in_progress_only() -> None:
    metadata = lane_task_card_metadata(
        node_id="lane:researcher",
        name="Researcher",
        status="in_progress",
        notes_path="outputs/normalized/epi.md",
        specialist_session_id=uuid4(),
        role="researcher",
    )
    patched = patch_open_lane_task_status(metadata, "cancelled")
    assert patched["streamItems"][0]["toolCall"]["status"] == "cancelled"
    already = patch_open_lane_task_status(patched, "failed")
    assert already["streamItems"][0]["toolCall"]["status"] == "cancelled"
