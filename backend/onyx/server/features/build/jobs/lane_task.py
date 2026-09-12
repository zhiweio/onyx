"""Parent-transcript cards for Craft job specialist lanes."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

LANE_TASK_NODE_KEY = "lane_task_node_id"
LANE_TASK_JOB_KEY = "lane_task_job_id"
_ACTIVITY_MAX = 120
_LEGACY_STATUSES = ("in_progress", "completed", "failed", "cancelled", "pending")
_SETTLED_STATUSES = frozenset({"completed", "failed", "cancelled"})

LaneTaskUpsertAction = Literal["update", "create", "settle_then_create"]


def lane_task_tool_id(node_id: str) -> str:
    return f"lane-task-{node_id}"


def lane_task_lookup_ids(node_id: str) -> tuple[str, ...]:
    """Stable id plus older cards that appended status to the tool id."""
    stable = lane_task_tool_id(node_id)
    return (stable, *(f"{stable}-{status}" for status in _LEGACY_STATUSES))


def lane_task_card_metadata(
    *,
    node_id: str,
    name: str,
    status: str,
    notes_path: str,
    specialist_session_id: UUID | None,
    role: str | None,
    job_id: UUID | None = None,
) -> dict[str, Any]:
    description = f"{name} — {notes_path}" if notes_path else name
    tool_id = lane_task_tool_id(node_id)
    tool_call: dict[str, Any] = {
        "id": tool_id,
        "kind": "task",
        "toolName": "task",
        "title": name,
        "description": description,
        "command": "",
        "status": status,
        "rawOutput": notes_path,
    }
    if role:
        tool_call["subagentType"] = role
    if specialist_session_id is not None:
        tool_call["subagentSessionId"] = str(specialist_session_id)
    if job_id is not None:
        tool_call["jobId"] = str(job_id)
    metadata: dict[str, Any] = {
        "type": "assistant_message",
        LANE_TASK_NODE_KEY: node_id,
        "streamItems": [
            {
                "type": "tool_call",
                "id": tool_id,
                "toolCall": tool_call,
            }
        ],
    }
    if job_id is not None:
        metadata[LANE_TASK_JOB_KEY] = str(job_id)
    return metadata


def _first_tool_call(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    items = metadata.get("streamItems")
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "tool_call":
            continue
        tool = item.get("toolCall")
        if isinstance(tool, dict):
            return tool
    return None


def lane_card_tool_status(metadata: dict[str, Any] | None) -> str:
    tool = _first_tool_call(metadata)
    if tool is None:
        return ""
    return str(tool.get("status") or "")


def lane_card_specialist_session_id(metadata: dict[str, Any] | None) -> str | None:
    tool = _first_tool_call(metadata)
    if tool is None:
        return None
    value = tool.get("subagentSessionId")
    if isinstance(value, str) and value:
        return value
    return None


def lane_card_job_id(metadata: dict[str, Any] | None) -> str | None:
    if isinstance(metadata, dict):
        raw = metadata.get(LANE_TASK_JOB_KEY)
        if isinstance(raw, str) and raw:
            return raw
    tool = _first_tool_call(metadata)
    if tool is None:
        return None
    value = tool.get("jobId")
    if isinstance(value, str) and value:
        return value
    return None


def lane_task_upsert_action(
    existing_metadata: dict[str, Any] | None,
    new_metadata: dict[str, Any],
) -> LaneTaskUpsertAction:
    """Update the same specialist card. Start a new card after cancel or a new job."""
    if existing_metadata is None:
        return "create"
    old_status = lane_card_tool_status(existing_metadata)
    old_session = lane_card_specialist_session_id(existing_metadata)
    new_session = lane_card_specialist_session_id(new_metadata)
    old_job = lane_card_job_id(existing_metadata)
    new_job = lane_card_job_id(new_metadata)
    if old_session or new_session:
        same_session = bool(old_session) and old_session == new_session
    else:
        same_session = True
    same_job = not old_job or not new_job or old_job == new_job
    if same_session and same_job and old_status not in _SETTLED_STATUSES:
        return "update"
    if old_status not in _SETTLED_STATUSES:
        return "settle_then_create"
    return "create"


def _first_line(text: str) -> str:
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if len(line) > _ACTIVITY_MAX:
        return f"{line[: _ACTIVITY_MAX - 1].rstrip()}…"
    return line


def patch_open_lane_task_status(
    metadata: dict[str, Any], status: str
) -> dict[str, Any]:
    """Set open lane-task cards to a terminal status. Leave settled cards."""
    items = metadata.get("streamItems")
    if not isinstance(items, list):
        return metadata
    changed = False
    next_items: list[Any] = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") != "tool_call":
            next_items.append(item)
            continue
        tool = item.get("toolCall")
        if not isinstance(tool, dict):
            next_items.append(item)
            continue
        current = str(tool.get("status") or "")
        if current in _SETTLED_STATUSES:
            next_items.append(item)
            continue
        next_items.append({**item, "toolCall": {**tool, "status": status}})
        changed = True
    if not changed:
        return metadata
    return {**metadata, "streamItems": next_items}


def activity_label_from_metadata(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    items = metadata.get("streamItems")
    if isinstance(items, list):
        for item in reversed(items):
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "tool_call":
                tool = item.get("toolCall")
                if isinstance(tool, dict):
                    label = _first_line(
                        str(
                            tool.get("description")
                            or tool.get("title")
                            or tool.get("command")
                            or ""
                        )
                    )
                    if label:
                        return label
            if kind in {"thinking", "text"}:
                label = _first_line(str(item.get("content") or ""))
                if label:
                    return label
    if metadata.get("type") == "tool_call_progress":
        label = _first_line(
            str(
                metadata.get("description")
                or metadata.get("title")
                or metadata.get("command")
                or ""
            )
        )
        if label:
            return label
    content = metadata.get("content")
    if isinstance(content, dict):
        label = _first_line(str(content.get("text") or content.get("content") or ""))
        if label:
            return label
    if isinstance(content, str):
        label = _first_line(content)
        if label:
            return label
    return None
