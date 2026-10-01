"""Platform-owned tool contract bridged into agent runtimes.

QM reference: ``harness-shared.ts`` ``bridgedTools`` — the canonical tool
format is ``name + description + JSON Schema parameters + execute`` and
every runtime adapts from it. On this side the catalog lives in the
api_server; agent runtimes reach it over MCP (opencode ``remote`` servers)
or the REST bridge. Tool calls and results are journaled and capped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# QM caps tool results at 100k chars before they enter the transcript.
MAX_TOOL_RESULT_CHARS = 100_000


@dataclass
class ToolInvocation:
    """One tool call as it arrives from an agent runtime."""

    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    sandbox_id: str | None = None


@dataclass
class ToolContext:
    """Who is calling and from where. Built per request by the bridge."""

    user_id: str
    tenant_id: str | None = None


@dataclass
class ToolResult:
    """Result in MCP content-block shape; ``terminate`` stops the turn."""

    content: list[dict[str, Any]] = field(default_factory=list)
    terminate: bool = False

    def text(self) -> str:
        parts = [
            block.get("text", "")
            for block in self.content
            if block.get("type") == "text"
        ]
        return "\n".join(parts)


def text_result(text: str, *, terminate: bool = False) -> ToolResult:
    return ToolResult(content=[{"type": "text", "text": text}], terminate=terminate)


def unavailable(tool_name: str, reason: str) -> ToolResult:
    return text_result(f"[{tool_name}] unavailable: {reason}")


def cap_result_text(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    """Cap tool result text before it enters any transcript or journal."""
    if len(text) <= limit:
        return text
    truncation_note = f"\n...[truncated {len(text) - limit} chars]"
    return text[:limit] + truncation_note


@runtime_checkable
class PlatformTool(Protocol):
    """The contract every platform tool satisfies."""

    name: str
    description: str
    parameters: dict[str, Any]

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult: ...
