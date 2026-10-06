"""Cinematic replay: tape events → the same packets the live stream produced.

Replay is a read-only second subscription over the fact ledger (dsh
discipline: live and replay share one translation/fold path). Each archived
harness event is fed through the SAME translator that produced it live:

- codex rows (``codex:<method>`` subtypes) drive ``translate_codex_event``
  with one ``CodexTurnState`` per turn — delta accumulation and item
  deduplication behave exactly as they did live.
- opencode rows drive ``translate_opencode_event`` with one ``_TurnState``
  per (turn, sessionID): the translator drops events whose sessionID does
  not match the state, and a restored sandbox carries a NEW
  ``opencode_session_id``, so the state key comes from the event itself.
  Subagent streams therefore replay as their own inline flow. All fetch
  callbacks stay None — settled message bodies are rebuilt from the
  recorded part stream.
- ``context_event`` rows become replay markers: ``compaction`` maps to a
  CompactionPacket, ``turn/start``/``turn/end`` to timeline markers the
  player uses for turn boundaries and interrupted badges.

Envelope serialization matches the live SSE wire format exactly
(``model_dump(mode="json", by_alias=True)``), so the frontend replays
through the same ``parsePacket → foldTurnStream`` pipeline it uses live.

Failure discipline: one dirty event skips (counted) instead of failing the
page — replay is an audit view.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from onyx.server.features.build.packets import CompactionPacket
from onyx.server.features.build.tape_archive.reader import merged_tape_events
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Replay reads tape events in pages of this many source rows.
REPLAY_PAGE_EVENTS = 400


class ReplayPacketItem(BaseModel):
    """One replay output row: a live-format packet, or a timeline marker."""

    source_id: int
    turn_index: int | None
    created_at: Any
    # "packet" rows carry the wire packet; "marker" rows carry the marker kind.
    type: str
    packet: dict[str, Any] | None = None
    marker: str | None = None
    reason: str | None = None


class ReplayPage(BaseModel):
    items: list[ReplayPacketItem]
    next_source_id: int | None
    skipped: int


def _opencode_session_key(raw: dict[str, Any], fallback: str) -> str:
    """The same sessionID extraction the opencode translator performs."""
    props = raw.get("properties")
    if isinstance(props, dict):
        sess_id = props.get("sessionID")
        if isinstance(sess_id, str) and sess_id:
            return sess_id
        info = props.get("info")
        if isinstance(info, dict):
            inner = info.get("sessionID")
            if isinstance(inner, str) and inner:
                return inner
    return fallback


def _dump(envelope: Any) -> dict[str, Any]:
    return envelope.model_dump(mode="json", by_alias=True)


def build_replay_packets(
    db_session: Session,
    session_id: UUID,
    *,
    after_source_id: int | None = None,
    turn_index: int | None = None,
    limit: int = REPLAY_PAGE_EVENTS,
) -> ReplayPage:
    """Translate one page of a session's tape into live-format packets."""
    # Imported lazily: the serve clients pull transport dependencies.
    from onyx.server.features.build.sandbox.codex.events import (
        CodexTurnState,
        translate_codex_event,
    )
    from onyx.server.features.build.sandbox.opencode.serve_client import (
        _TurnState,
        translate_opencode_event,
    )

    limit = max(1, min(limit, 2000))
    events = merged_tape_events(
        db_session,
        session_id,
        after_source_id=after_source_id,
        limit=limit,
    )
    items: list[ReplayPacketItem] = []
    skipped = 0
    # Translation state never crosses a turn or (for opencode) a sessionID.
    codex_states: dict[Any, CodexTurnState] = {}
    opencode_states: dict[tuple[Any, str], _TurnState] = {}
    openai_fallback_key = "__replay_main__"

    for event in events:
        try:
            row_turn = event["turn_index"]
            if turn_index is not None and row_turn != turn_index:
                continue
            payload: dict[str, Any] = event["payload"]
            base = {
                "source_id": event["source_id"],
                "turn_index": row_turn,
                "created_at": event["created_at"],
            }
            if event["kind"] == "context_event":
                subtype = event["subtype"]
                if subtype == "compaction":
                    summary = payload.get("summary")
                    items.append(
                        ReplayPacketItem(
                            **base,
                            type="packet",
                            packet=_dump(
                                CompactionPacket(
                                    summary=summary
                                    if isinstance(summary, str)
                                    else None
                                )
                            ),
                        )
                    )
                elif subtype in ("turn/start", "turn/end"):
                    items.append(
                        ReplayPacketItem(
                            **base,
                            type="marker",
                            marker="turn_start"
                            if subtype == "turn/start"
                            else "turn_end",
                            reason=payload.get("reason")
                            if isinstance(payload.get("reason"), str)
                            else None,
                        )
                    )
                # Other context events (turn_error) stay replay-invisible.
                continue

            if event["runtime"] == "codex":
                state = codex_states.get(row_turn)
                if state is None:
                    state = CodexTurnState(thread_id=str(session_id))
                    codex_states[row_turn] = state
                method = event["subtype"].removeprefix("codex:")
                items.extend(
                    ReplayPacketItem(**base, type="packet", packet=_dump(envelope))
                    for envelope in translate_codex_event(method, payload, state)
                )
            elif event["runtime"] == "opencode":
                key = (row_turn, _opencode_session_key(payload, openai_fallback_key))
                state = opencode_states.get(key)
                if state is None:
                    state = _TurnState(session_id=key[1])
                    opencode_states[key] = state
                items.extend(
                    ReplayPacketItem(**base, type="packet", packet=_dump(envelope))
                    for envelope in translate_opencode_event(payload, state)
                )
            else:
                # Unknown/eval runtimes: not replayable through translators.
                skipped += 1
        except Exception:
            skipped += 1
            logger.warning(
                "Replay skipped tape event %r for session %s",
                event,
                session_id,
                exc_info=True,
            )

    next_source_id = (
        events[-1]["source_id"] if len(events) >= limit and events else None
    )
    return ReplayPage(items=items, next_source_id=next_source_id, skipped=skipped)
