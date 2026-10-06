"""Thread-scoped tape recorder: raw harness events, verbatim.

One turn runner thread owns the recording: the drain loop records each
raw event BEFORE translation, and the persistence path flushes the buffer
into ``craft_tape_entry`` inside its own commit cadence. A contextvar
binds the two without changing any generator signature — the opencode
event path stays byte-equivalent when taping is off or the recorder is
unset (live-attach viewers, background replays).

Turn lifecycle follows the dsh fact-ledger discipline: entry records a
``turn/start`` context event (carrying the request environment so replay
can reconstruct what the model saw), and the executor notes
``turn/end`` with a reason on every owned exit. A turn whose runner died
without a note stays open on tape; readers classify it as interrupted.

Failure discipline: recording and flushing never raise into the turn
path; the tape is an audit/replay asset, not a correctness dependency.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import Any, Iterator
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

# Turn-end reasons, aligned with dsh's TurnEndReason vocabulary where the
# concepts overlap (completed / aborted / error / interrupted); the hard
# time budget is an Onyx-native outcome kept distinct from error.
TURN_END_COMPLETED = "completed"
TURN_END_ABORTED = "aborted"
TURN_END_ERROR = "error"
TURN_END_DEADLINE = "deadline_exceeded"
TURN_END_INTERRUPTED = "interrupted"


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

    def note_turn_end(self, reason: str, detail: str | None = None) -> None:
        payload: dict[str, Any] = {
            "turn_index": self.turn_index,
            "runtime": self.runtime,
            "reason": reason,
        }
        if detail:
            payload["detail"] = detail[:512]
        self._buffer.append(("context:turn/end", payload))

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
def tape_recording(
    session_id: UUID,
    turn_index: int,
    runtime: str,
    *,
    turn_id: UUID | None = None,
    kind: str | None = None,
    request_env: dict[str, Any] | None = None,
) -> Iterator[_TapeRecorder | None]:
    """Bind a recorder for this thread's turn, if taping is enabled.

    Records the ``turn/start`` fact on entry (request environment included,
    so the log alone can reconstruct what the model was asked with) and
    yields the recorder for the executor to note the turn-end reason.
    """
    from onyx.server.features.build.configs import CRAFT_TAPE_ENABLED

    if not CRAFT_TAPE_ENABLED:
        yield None
        return
    recorder = _TapeRecorder(session_id, turn_index, runtime)
    start_payload: dict[str, Any] = {"turn_index": turn_index, "runtime": runtime}
    if turn_id is not None:
        start_payload["turn_id"] = str(turn_id)
    if kind is not None:
        start_payload["kind"] = kind
    if request_env:
        start_payload["request_env"] = request_env
    recorder.record_context("turn/start", start_payload)
    token = _recorder.set(recorder)
    try:
        yield recorder
    finally:
        _recorder.reset(token)
        # Last-chance flush: the caller normally flushed on the turn's own
        # commits; anything left (turn/end note, a crash-tail prefix) is
        # persisted through a fresh session so the committed prefix on tape
        # matches what actually happened. Never raises into the turn path.
        if recorder._buffer:
            try:
                from onyx.db.engine.sql_engine import (
                    get_session_with_current_tenant,
                )

                with get_session_with_current_tenant() as db_session:
                    recorder.flush(db_session)
                    db_session.commit()
            except Exception:
                logger.warning(
                    "Tape buffer dropped %s unflushed entries for session %s",
                    len(recorder._buffer),
                    session_id,
                    exc_info=True,
                )


def record_raw_event(raw: dict[str, Any]) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.record_raw(raw)


def record_context_event(subtype: str, payload: dict[str, Any]) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.record_context(subtype, payload)


def note_turn_end(reason: str, detail: str | None = None) -> None:
    """Note the turn-end reason on the bound recorder, if any."""
    recorder = _recorder.get()
    if recorder is not None:
        recorder.note_turn_end(reason, detail)


def flush_tape(db_session: Session) -> None:
    recorder = _recorder.get()
    if recorder is not None:
        recorder.flush(db_session)
