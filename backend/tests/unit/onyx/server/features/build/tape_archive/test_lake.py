"""Craft tape archive lake writes and reads against a local file warehouse."""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from onyx.server.features.build.tape_archive.lake.catalog import (
    ensure_craft_tape_iceberg_tables,
    reset_lake_for_tests,
)
from onyx.server.features.build.tape_archive.lake.io import (
    TapeEventRecord,
    TurnRecord,
    append_tape_events,
    append_turns,
    clear_tenant_tape,
    expire_before,
    load_events,
    load_turns,
    read_event_window,
    session_aggregates,
    stats_windowed,
)


@pytest.fixture
def isolated_lake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    monkeypatch.setenv(
        "CRAFT_TAPE_ICEBERG_WAREHOUSE", f"file://{tmp_path / 'warehouse'}"
    )
    monkeypatch.setenv(
        "CRAFT_TAPE_ICEBERG_CATALOG_URI", f"sqlite:///{tmp_path / 'catalog.db'}"
    )
    reset_lake_for_tests()
    ensure_craft_tape_iceberg_tables()
    try:
        yield
    finally:
        clear_tenant_tape(tenant_id="public")
        reset_lake_for_tests()


def _event(session_id: str, source_id: int, **overrides: object) -> TapeEventRecord:
    defaults: dict[str, object] = {
        "session_id": session_id,
        "turn_index": 0,
        "source_id": source_id,
        "kind": "harness_message",
        "subtype": "message.part.updated",
        "runtime": "codex",
        "payload": {"seq": source_id},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return TapeEventRecord(**defaults)  # type: ignore[arg-type]


def _turn(session_id: str, turn_index: int, **overrides: object) -> TurnRecord:
    defaults: dict[str, object] = {
        "session_id": session_id,
        "turn_index": turn_index,
        "runtime": "codex",
        "user_id": None,
        "origin": "interactive",
        "started_at": datetime.now(timezone.utc),
        "ended_at": datetime.now(timezone.utc),
        "event_count": 3,
        "input_tokens": 100,
        "output_tokens": 40,
        "reasoning_tokens": None,
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "cost": 0.01,
        "turn_end_reason": "completed",
        "error_detail": None,
        "model": "test-model",
    }
    defaults.update(overrides)
    return TurnRecord(**defaults)  # type: ignore[arg-type]


def test_event_round_trip_and_cursor(isolated_lake: None) -> None:  # noqa: ARG001
    session = "s-1"
    records = [_event(session, source_id) for source_id in (1, 2, 3)]
    append_tape_events(records, batch_id="b1", tenant_id="public")

    page_one = load_events(session, limit=2, tenant_id="public")
    assert [record.source_id for record in page_one] == [1, 2]

    page_two = load_events(
        session, after_source_id=page_one[-1].source_id, limit=2, tenant_id="public"
    )
    assert [record.source_id for record in page_two] == [3]
    assert page_two[0].payload == {"seq": 3}

    turn_filtered = load_events(session, turn_index=9, tenant_id="public")
    assert turn_filtered == []


def test_event_window(isolated_lake: None) -> None:  # noqa: ARG001
    session = "s-2"
    append_tape_events(
        [_event(session, source_id) for source_id in range(1, 6)],
        batch_id="b1",
        tenant_id="public",
    )
    target, window = read_event_window(
        session, 3, before=1, after=1, tenant_id="public"
    )
    assert target is not None and target.source_id == 3
    assert [record.source_id for record in window] == [2, 3, 4]

    missing, empty = read_event_window(session, 99, tenant_id="public")
    assert missing is None and empty == []


def test_turn_dedupe_prefers_settled_copy(isolated_lake: None) -> None:  # noqa: ARG001
    session = "s-3"
    append_turns(
        [_turn(session, 0, turn_end_reason=None)],
        batch_id="b1",
        tenant_id="public",
    )
    # A batch retry appends the same turn again, now with its end reason.
    append_turns(
        [_turn(session, 0, turn_end_reason="completed")],
        batch_id="b2",
        tenant_id="public",
    )
    turns = load_turns(session, tenant_id="public")
    assert len(turns) == 1
    assert turns[0].turn_end_reason == "completed"


def test_session_aggregates_and_stats(isolated_lake: None) -> None:  # noqa: ARG001
    append_turns(
        [
            _turn("s-a", 0),
            _turn("s-a", 1, turn_end_reason="error", cost=0.0, output_tokens=10),
            _turn("s-b", 0),
        ],
        batch_id="b1",
        tenant_id="public",
    )
    aggregates = session_aggregates(tenant_id="public")
    assert set(aggregates) == {"s-a", "s-b"}
    assert aggregates["s-a"].turns == 2
    assert aggregates["s-a"].events == 6
    assert aggregates["s-a"].last_reason == "error"

    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    stats = stats_windowed(from_time=start, to_time=end, tenant_id="public")
    assert stats["turns"] == 3
    assert stats["sessions"] == 2
    assert stats["by_reason"]["completed"] == 2
    assert stats["by_reason"]["error"] == 1


def test_expire_before(isolated_lake: None) -> None:  # noqa: ARG001
    old = datetime.now(timezone.utc) - timedelta(days=400)
    append_tape_events(
        [_event("s-old", 1, created_at=old)],
        batch_id="b1",
        tenant_id="public",
    )
    append_turns(
        [_turn("s-old", 0, started_at=old, ended_at=old)],
        batch_id="b1",
        tenant_id="public",
    )
    append_tape_events([_event("s-new", 2)], batch_id="b2", tenant_id="public")
    append_turns([_turn("s-new", 0)], batch_id="b2", tenant_id="public")

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    expired = expire_before(cutoff, tenant_id="public")
    assert expired == 1
    assert load_events("s-old", tenant_id="public") == []
    assert load_events("s-new", tenant_id="public") != []
