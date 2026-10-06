"""Read-side pairing analysis for tape tool calls (dsh call→result parity).

Scans one session's event stream and pairs each tool call with its result
across both craft runtimes:

- opencode raw events: ``message.part.updated`` parts carry ``toolCallId``
  with a terminal ``status`` (``completed`` / ``failed``); the call start
  is the first part seen for that id.
- codex raw events (``codex:item/completed``): items of type
  ``tool_call`` / ``command_execution`` / ``web_search`` carry the call
  id; the function-call output arrives as a later ``tool_call`` item's
  counterpart (the harness reports them together, so a call without a
  recorded counterpart is an unmatched call).

A call without a result inside an open turn (a ``turn/start`` context
event with no matching ``turn/end``, or an end whose reason is
``aborted``/``interrupted``) marks as interrupted, mirroring dsh's
synthetic closer semantics — the outcome is unknown, not failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from onyx.server.features.build.sandbox.tape_recorder import (
    TURN_END_ABORTED,
    TURN_END_INTERRUPTED,
)

_UNMATCHED_END_REASONS = frozenset({TURN_END_ABORTED, TURN_END_INTERRUPTED})

# opencode part statuses that settle a tool call.
_OPENCODE_DONE_STATUSES = frozenset({"completed", "failed"})

# codex item types that represent a settled tool invocation.
_CODEX_CALL_ITEM_TYPES = frozenset({"tool_call", "command_execution", "web_search"})


@dataclass
class CallPair:
    call_id: str
    runtime: str
    start_source_id: int | None = None
    end_source_id: int | None = None
    tool_name: str | None = None
    interrupted: bool = False


@dataclass
class PairingResult:
    """Pairing annotations for one session, keyed by call id."""

    pairs: dict[str, CallPair] = field(default_factory=dict)
    # Source ids of open turns (turn/start with no turn/end), used by the
    # UI to badge interrupted work.
    open_turn_starts: set[int] = field(default_factory=set)

    def annotations_for(self, source_id: int) -> list[str]:
        """UI hints for one event row: pair partner and interrupted badge."""
        hints: list[str] = []
        for pair in self.pairs.values():
            if pair.start_source_id == source_id and pair.end_source_id is not None:
                hints.append(f"call:{pair.call_id}")
            elif pair.end_source_id == source_id:
                hints.append(f"result:{pair.call_id}")
            elif pair.start_source_id == source_id and pair.interrupted:
                hints.append(f"call:{pair.call_id}")
                hints.append("interrupted")
        return hints


def _pair_opencode_part(
    payload: dict[str, Any], state: PairingResult, sid: int
) -> None:
    part = payload.get("part")
    if not isinstance(part, dict):
        return
    call_id = part.get("toolCallId")
    if not isinstance(call_id, str) or not call_id:
        return
    status = part.get("status")
    pair = state.pairs.get(call_id)
    if pair is None:
        pair = CallPair(call_id=call_id, runtime="opencode")
        state.pairs[call_id] = pair
    pair.tool_name = pair.tool_name or (
        part.get("tool") if isinstance(part.get("tool"), str) else None
    )
    if pair.start_source_id is None:
        pair.start_source_id = sid
    if status in _OPENCODE_DONE_STATUSES and pair.end_source_id is None:
        pair.end_source_id = sid


def _pair_codex_item(payload: dict[str, Any], state: PairingResult, sid: int) -> None:
    item = payload.get("item")
    if not isinstance(item, dict):
        return
    if item.get("type") not in _CODEX_CALL_ITEM_TYPES:
        return
    call_id = item.get("id")
    if not isinstance(call_id, str) or not call_id:
        return
    # A completed codex item is the settled call+result together; record
    # both endpoints at this row.
    pair = state.pairs.get(call_id)
    if pair is None:
        pair = CallPair(call_id=call_id, runtime="codex")
        state.pairs[call_id] = pair
    pair.tool_name = pair.tool_name or (
        item.get("tool")
        if isinstance(item.get("tool"), str)
        else (item.get("name") if isinstance(item.get("name"), str) else None)
    )
    if pair.start_source_id is None:
        pair.start_source_id = sid
    pair.end_source_id = sid


def analyze_pairings(events: list[Any]) -> PairingResult:
    """Fold ordered tape events (ascending source_id) into call pairings.

    ``events`` are rows or records exposing ``kind``, ``subtype``,
    ``payload`` and ``source_id``.
    """
    state = PairingResult()
    # Per turn: turn_index -> (start_source_id, end_reason | None)
    open_turns: dict[int, tuple[int, str | None]] = {}

    for event in events:
        sid = event.source_id
        payload = event.payload or {}
        if event.kind == "context_event":
            if event.subtype == "turn/start":
                turn_index = payload.get("turn_index")
                if isinstance(turn_index, int):
                    open_turns[turn_index] = (sid, None)
            elif event.subtype == "turn/end":
                turn_index = payload.get("turn_index")
                if isinstance(turn_index, int) and turn_index in open_turns:
                    open_turns[turn_index] = (
                        open_turns[turn_index][0],
                        payload.get("reason"),
                    )
            continue
        if event.kind != "harness_message":
            continue
        if event.subtype == "message.part.updated":
            _pair_opencode_part(payload, state, sid)
        elif event.subtype in ("codex:item/completed", "codex:item/added"):
            _pair_codex_item(payload, state, sid)

    for start_sid, reason in open_turns.values():
        if reason is None or reason in _UNMATCHED_END_REASONS:
            state.open_turn_starts.add(start_sid)

    for pair in state.pairs.values():
        if pair.end_source_id is None and state.open_turn_starts:
            pair.interrupted = True
    return state
