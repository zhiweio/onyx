"""Tape recorder turn lifecycle: start fact, end note, crash stays open."""

from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

import onyx.server.features.build.sandbox.tape_recorder as tape_recorder_module
from onyx.server.features.build.sandbox.tape_recorder import (
    TURN_END_COMPLETED,
    tape_recording,
)


class _FakeSession:
    """Absorbs flush calls; the recorder never persists on its own."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(self, entry: Any) -> None:
        self.entries.append(entry.__dict__)


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def fake_append(_db_session: Any, **kwargs: Any) -> None:
        entries.append(kwargs)

    monkeypatch.setattr(tape_recorder_module, "append_tape_entry", fake_append)
    monkeypatch.setattr(tape_recorder_module, "CRAFT_TAPE_ENABLED", True, raising=False)
    # The configs module the context manager re-reads at runtime.
    import onyx.server.features.build.configs as build_configs

    monkeypatch.setattr(build_configs, "CRAFT_TAPE_ENABLED", True, raising=False)
    return entries


def test_turn_start_recorded_and_flushed(captured: list[dict[str, Any]]) -> None:
    session_id = uuid4()
    fake_db = _FakeSession()
    with tape_recording(
        session_id,
        3,
        "codex",
        turn_id=uuid4(),
        kind="prompt",
        request_env={"provider": "p", "model": "m", "reasoning_effort": "high"},
    ) as rec:
        assert rec is not None
        rec.record_raw({"type": "message.part.updated", "part": {}})
        rec.flush(cast(Session, fake_db))
    subtypes = [entry["subtype"] for entry in captured]
    assert subtypes == ["turn/start", "message.part.updated"]
    start = captured[0]
    assert start["kind"] == "context_event"
    assert start["turn_index"] == 3
    assert start["payload"]["runtime"] == "codex"
    assert start["payload"]["request_env"]["model"] == "m"
    assert start["payload"]["kind"] == "prompt"


def test_note_turn_end_appends_end_fact(captured: list[dict[str, Any]]) -> None:
    session_id = uuid4()
    fake_db = _FakeSession()
    with tape_recording(session_id, 0, "opencode") as rec:
        assert rec is not None
        tape_recorder_module.note_turn_end(TURN_END_COMPLETED)
        rec.flush(cast(Session, fake_db))
    subtypes = [entry["subtype"] for entry in captured]
    assert subtypes == ["turn/start", "turn/end"]
    end = captured[1]
    assert end["payload"]["reason"] == "completed"


def test_crash_exit_leaves_turn_open(captured: list[dict[str, Any]]) -> None:
    session_id = uuid4()
    fake_db = _FakeSession()
    with pytest.raises(RuntimeError):
        with tape_recording(session_id, 0, "codex") as rec:
            assert rec is not None
            rec.record_raw({"type": "message.part.updated"})
            rec.flush(cast(Session, fake_db))
            raise RuntimeError("runner died")
    # Only the start fact: readers classify this turn as interrupted.
    subtypes = [entry["subtype"] for entry in captured]
    assert subtypes == ["turn/start", "message.part.updated"]


def test_disabled_taping_yields_none(captured: list[dict[str, Any]]) -> None:
    import onyx.server.features.build.configs as build_configs

    build_configs.CRAFT_TAPE_ENABLED = False
    try:
        with tape_recording(uuid4(), 0, "codex") as rec:
            assert rec is None
            tape_recorder_module.record_raw_event({"type": "x"})
            tape_recorder_module.note_turn_end("completed")
    finally:
        build_configs.CRAFT_TAPE_ENABLED = True
    assert captured == []
