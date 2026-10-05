"""Rebuild a codex thread's history from the platform tape.

codex sessions run one ephemeral thread per turn; the tape is the only
source of prior items. ``build_inject_items`` reassembles the recorded
codex items into ``thread/inject_items`` payloads (Responses-API style),
with the two fixes qm learned the hard way: call ids over 64 chars are
hashed, and a function call without its output gets an explicit
placeholder so the injected transcript stays valid.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_tape import load_tape_entries

# Inject budget: bound the replay so a long session can't blow the fresh
# thread's context. Codex items are compact; 400 is ~a long session.
_MAX_INJECT_ITEMS = 400

_INTERRUPTED_TOOL_RESULT = "[interrupted before this tool returned]"

_INJECTABLE_ITEM_TYPES = frozenset(
    {"agentMessage", "reasoning", "command_execution", "tool_call", "web_search"}
)


def _normalized_call_id(call_id: str) -> str:
    if len(call_id) <= 64:
        return call_id
    return "call_" + hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:59]


def tape_item_to_inject(item: dict[str, Any]) -> dict[str, Any] | None:
    """One recorded codex item → one inject item; None when not injectable."""
    item_type = item.get("type")
    if item_type == "agentMessage":
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }
    if item_type in {"command_execution", "tool_call", "web_search"}:
        call_id = str(item.get("id") or "")
        name = str(item.get("tool") or item.get("name") or "tool")
        arguments = item.get("input") or item.get("arguments") or {}
        if not isinstance(arguments, str):
            import json

            try:
                arguments = json.dumps(arguments, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                arguments = "{}"
        return {
            "type": "function_call",
            "call_id": _normalized_call_id(call_id),
            "name": name,
            "arguments": arguments,
        }
    return None


def build_inject_items(
    db_session: Session, session_id: UUID, *, limit: int = _MAX_INJECT_ITEMS
) -> list[dict[str, Any]]:
    """Codex-native replay: recorded items → inject payload.

    Function calls whose matching output is missing (turn was interrupted)
    get the placeholder so codex accepts the transcript."""
    rows = load_tape_entries(
        db_session, session_id, kinds=["harness_message"], limit=limit
    )
    inject: list[dict[str, Any]] = []
    pending_calls: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.runtime != "codex":
            continue
        # The tape stores codex subtypes with a "codex:" prefix on the raw
        # type; normalize here so both writers stay as-is.
        subtype = row.subtype.removeprefix("codex:")
        if subtype != "item/completed":
            continue
        item = (row.payload or {}).get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "userMessage":
            content = item.get("content")
            text = None
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        text = part["text"]
                        break
            if isinstance(content, str):
                text = content
            if text:
                inject.append(
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": text}],
                    }
                )
            continue
        if item_type not in _INJECTABLE_ITEM_TYPES:
            continue
        converted = tape_item_to_inject(item)
        if converted is None:
            continue
        inject.append(converted)
        if converted.get("type") == "function_call":
            pending_calls[converted["call_id"]] = converted

        output = item.get("output") or item.get("result")
        if output is not None:
            call_id = _normalized_call_id(str(item.get("id") or ""))
            inject.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output if isinstance(output, str) else str(output),
                }
            )
            pending_calls.pop(call_id, None)

    inject.extend(
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": _INTERRUPTED_TOOL_RESULT,
        }
        for call_id in list(pending_calls)
    )
    return inject


def build_preamble_from_tape(
    db_session: Session,
    session_id: UUID,
    *,
    char_budget: int = 16_000,
) -> str | None:
    """Cross-runtime migration preamble: flatten the tape to text.

    Used when a session switches runtime family (opencode ↔ codex): the
    new harness gets one context-setting user preamble instead of native
    items it cannot replay."""
    rows = load_tape_entries(db_session, session_id, kinds=["harness_message"])
    lines: list[str] = []
    for row in rows:
        if row.runtime == "codex":
            item = (row.payload or {}).get("item")
            if isinstance(item, dict):
                if item.get("type") == "userMessage":
                    content = item.get("content")
                    if isinstance(content, str):
                        lines.append(f"User: {content}")
                elif item.get("type") == "agentMessage":
                    text = item.get("text")
                    if isinstance(text, str):
                        lines.append(f"Assistant: {text}")
        else:
            event_type = row.subtype
            if event_type == "message.part.updated":
                payload = row.payload or {}
                part = payload.get("part") or {}
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    role = (
                        "Assistant"
                        if (payload.get("info") or {}).get("role") == "assistant"
                        else "User"
                    )
                    lines.append(f"{role}: {text}")
    if not lines:
        return None
    body = "\n".join(lines)
    if len(body) > char_budget:
        body = body[-char_budget:]
    return (
        "The previous conversation ran on another agent runtime. "
        "Continue from this summary of it; do not redo finished work:\n\n" + body
    )
