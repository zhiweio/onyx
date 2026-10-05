"""Thread-scoped tape recorder: raw harness events, verbatim.

One turn runner thread owns the recording: the drain loop records each
raw event BEFORE translation, and the persistence path flushes the buffer
into ``craft_tape_entry`` inside its own commit cadence. A contextvar
binds the two without changing any generator signature — the opencode
event path stays byte-equivalent when taping is off or the recorder is
unset (live-attach viewers, background replays).

Failure discipline: recording and flushing never raise into the turn
path; the tape is an audit/replay asset, not a correctness dependency.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_tape import append_tape_entry
from onyx.utils.logger import setup_logger

logger = setup_logger()

_recorder: ContextVar["_TapeRecorder | None"] = ContextVar(
    "craft_tape_recorder", default=None
)

# opencode bus-internal frames that carry no model-visible information.
_SKIP_RAW_TYPES = frozenset({"server.connected"})


class _TapeRecorder:
    __slots__ = ("session_id", "turn_index", "runtime", "_buffer", "_token")

    def __init__(self, session_id: UUID, turn_index: int, runtime: str) -> None:
        self.session_id = session_id
        self.turn_index = turn_index
        self.runtime = runtime
        self._buffer: list[tuple[str, dict[str, Any]]] = []
        self._token: Any = None

    def record_raw(self, raw: dict[str, Any]) -> None:
        event_type = raw.get("type")
        if not isinstance(event_type, str) or event_type in _SKIP_RAW_TYPES:
            return
        self._buffer.append((event_type, raw))

    def record_context(self, subtype: str, payload: dict[str, Any]) -> None:
        self._buffer.append((f"context:{subtype}", payload))

    def flush(self, db_session: Session) -> None:
        if not self._buffer:
            return
        pending, self._buffer = self._buffer, []
        for subtype, payload in pending:
            kind = (
                "context_event" if subtype.startswith("context:") else "harness_message"
            )
            append_tape_entry(
                db_session,
                session_id=self.session_id,
                turn_index=self.turn_index,
                kind=kind,
                subtype=subtype.removeprefix("context:"),
                runtime=self.runtime,
                payload=payload,
            )


@contextlib.contextmanager
def tape_recording(session_id: UUID, turn_index: int, runtime: str) -> Any:
    """Bind a recorder for this thread's turn, if taping is enabled."""
    from onyx.server.features.build.configs import CRAFT_TAPE_ENABLED

    if not CRAFT_TAPE_ENABLED:
        yield
        return
    recorder = _TapeRecorder(session_id, turn_index, runtime)
    token = _recorder.set(recorder)
    try:
        yield
    finally:
        _recorder.reset(token)
        # Last-chance flush safety: the caller normally flushed; anything
        # left is dropped with a log rather than raising out of the turn.
        if recorder._buffer:
            logger.warning(
                "Tape buffer dropped %s unflushed entries for session %s",
                len(recorder._buffer),
                session_id,
            )


def record_raw_event(raw: dict[str, Any]) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.record_raw(raw)


def record_context_event(subtype: str, payload: dict[str, Any]) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.record_context(subtype, payload)


def flush_tape(db_session: Session) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.flush(db_session)
