"""codex notification → SandboxEvent translation.

Pure function over the notification payloads qm verified against codex
0.156.x (camel/snake tolerant on usage fields). State tracks item text
dedup, token-usage totals (replayed totals are dropped), and the finish
reason for the terminator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from onyx.server.features.build.packets import ContextUsagePacket
from onyx.server.features.build.sandbox.event_schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    Error,
    PromptResponse,
    ToolCallProgress,
    ToolCallStart,
)
from onyx.server.features.build.sandbox.sse import SSEKeepalive

_TURN_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "interrupted", "cancelled", "canceled"}
)
_STOP_REASON_BY_STATUS = {
    "completed": "end_turn",
    "failed": "refusal",
    "interrupted": "cancelled",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


@dataclass
class CodexTurnState:
    thread_id: str
    seen_item_ids: set[str] = field(default_factory=set)
    seen_tool_calls: set[str] = field(default_factory=set)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    terminated: bool = False
    item_texts: dict[str, str] = field(default_factory=dict)


def _number(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _camel_or_snake(payload: dict[str, Any], camel: str, snake: str) -> Any:
    return payload.get(camel, payload.get(snake))


def _usage_packet(
    state: CodexTurnState, params: dict[str, Any]
) -> ContextUsagePacket | None:
    """thread/tokenUsage/updated → granular usage packet, deduped.

    Totals arrive repeatedly with the same or slightly-grown values; only
    strictly-growing totals pass through (qm's dedup rule)."""
    usage = params.get("tokenUsage") or params.get("token_usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total") or {}
    last = usage.get("last") or {}
    total_input = _number(
        _camel_or_snake(total, "inputTokens", "input_tokens")
    ) + _number(_camel_or_snake(total, "cachedInputTokens", "cached_input_tokens"))
    total_output = _number(_camel_or_snake(total, "outputTokens", "output_tokens"))
    if (
        total_input <= state.total_input_tokens
        and total_output <= state.total_output_tokens
    ):
        return None
    last_input = _number(_camel_or_snake(last, "inputTokens", "input_tokens"))
    cached_total = _number(
        _camel_or_snake(total, "cachedInputTokens", "cached_input_tokens")
    )
    input_tokens = last_input or max(0, total_input - state.total_input_tokens)
    output_tokens = max(0, total_output - state.total_output_tokens)
    state.total_input_tokens = total_input
    state.total_output_tokens = total_output
    state.total_cached_tokens = cached_total
    used = input_tokens + output_tokens
    if used <= 0:
        return None
    return ContextUsagePacket(
        used_tokens=used,
        cost=None,
        message_id=f"{state.thread_id}:{total_output}",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


def _tool_events(
    state: CodexTurnState, item: dict[str, Any]
) -> Iterable[ToolCallStart | ToolCallProgress]:
    """A completed tool-execution item → start+progress pair (codex reports
    tools only at completion; the pair keeps the timeline card shape)."""
    call_id = str(item.get("id") or "")
    name = str(item.get("tool") or item.get("name") or "codex_tool")
    if not call_id or call_id in state.seen_tool_calls:
        return
    state.seen_tool_calls.add(call_id)
    status = "failed" if item.get("status") == "failed" else "completed"
    common = {
        "toolCallId": call_id,
        "title": name,
        "kind": "execute"
        if name in {"shell", "apply_patch", "local_shell"}
        else "other",
        "status": "pending",
        "_meta": {"toolName": name},
    }
    yield ToolCallStart.model_validate({"sessionUpdate": "tool_call", **common})
    finished = dict(common)
    finished["status"] = status
    output = item.get("output") or item.get("result")
    if isinstance(output, str):
        finished["rawOutput"] = output
    yield ToolCallProgress.model_validate(
        {"sessionUpdate": "tool_call_update", **finished}
    )


def translate_codex_event(
    method: str,
    params: dict[str, Any],
    state: CodexTurnState,
) -> Iterable[Any]:
    """One codex notification → zero or more sandbox events.

    Unknown notifications are ignored: the protocol grows faster than any
    consumer, and silence is safer than a crash in the turn loop."""
    if state.terminated:
        return

    if method == "item/agentMessage/delta":
        delta = params.get("delta")
        if isinstance(delta, str) and delta:
            item_id = str(params.get("itemId") or "")
            state.item_texts[item_id] = state.item_texts.get(item_id, "") + delta
            yield AgentMessageChunk.model_validate(
                {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": delta},
                }
            )
        return

    if method in ("item/started", "item/completed"):
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = item.get("type")
        item_id = str(item.get("id") or "")
        if method == "item/completed":
            if item_type == "reasoning":
                for summary in item.get("summary") or []:
                    if isinstance(summary, str) and summary:
                        yield AgentThoughtChunk.model_validate(
                            {
                                "sessionUpdate": "agent_thought_chunk",
                                "content": {"type": "text", "text": summary},
                            }
                        )
            elif item_type in {"command_execution", "tool_call", "web_search"}:
                yield from _tool_events(state, item)
            elif item_type == "agentMessage":
                # completed agent messages were already streamed as deltas;
                # commentary-phase text arrives ONLY here.
                phase = item.get("phase")
                if phase == "commentary" and item_id not in state.item_texts:
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        yield AgentMessageChunk.model_validate(
                            {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": text},
                            }
                        )
            elif item_type == "error":
                message = item.get("message") or "codex reported an error"
                yield Error.model_validate({"code": -1, "message": str(message)})
                return
        return

    if method == "thread/tokenUsage/updated":
        packet = _usage_packet(state, params)
        if packet is not None:
            yield packet
        return

    if method == "turn/completed":
        state.terminated = True
        turn = params.get("turn") or {}
        status = str(turn.get("status") or "completed")
        if status == "failed":
            error = turn.get("error") or {}
            message = (
                error.get("message") if isinstance(error, dict) else str(error)
            ) or "codex turn failed"
            yield Error.model_validate({"code": -1, "message": str(message)})
            return
        yield PromptResponse.model_validate(
            {"stopReason": _STOP_REASON_BY_STATUS.get(status, "end_turn")}
        )
        return

    if method == "codex/exit":
        # The bridge process died mid-turn; surface as transport failure.
        state.terminated = True
        yield Error.model_validate(
            {"code": -3, "message": "codex app-server exited during the turn"}
        )
        return

    # Unknown notification: ignored by design.


__all__ = [
    "CodexTurnState",
    "SSEKeepalive",
    "translate_codex_event",
]
