"""Concrete platform tools.

Each tool takes its service bindings through the constructor so tests
inject fakes and milestones bind real services incrementally:

- M2: catalog + bridge machinery live; ``rag_search`` runs against an
  injected retrieval callable; ``question`` parks through a per-session
  hook; the rest report structured ``unavailable`` reasons.
- M3 (scenario layer) binds the permission-aware retrieval pipeline.
- M5 (connectors) binds ``connector_query``.
- M6 (MCP gateway / realtime) binds ``mcp_call``, ``web_search``, ``crawl``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from onyx.server.features.build.tools.base import (
    ToolContext,
    ToolInvocation,
    ToolResult,
    text_result,
    unavailable,
)

# ── rag_search ────────────────────────────────────────────────────────────

SearchFn = Callable[[str, list[str], int, ToolContext], list[dict[str, Any]]]


class RagSearchTool:
    name = "rag_search"
    description = (
        "Search the company knowledge base (indexed documents) with "
        "permission-aware retrieval. Returns document titles, snippets and "
        "links. Use before answering questions about internal documents, "
        "policies, reports or historical data."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query; natural language works.",
            },
            "document_sets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional document set names to restrict to.",
            },
            "max_hits": {
                "type": "integer",
                "description": "Maximum documents to return (default 8).",
            },
        },
        "required": ["query"],
    }

    def __init__(self, search_fn: SearchFn | None = None) -> None:
        self._search_fn = search_fn

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        query = str(invocation.arguments.get("query", "")).strip()
        if not query:
            return text_result("[rag_search] argument 'query' is required")
        document_sets = [
            str(item)
            for item in invocation.arguments.get("document_sets", [])
            if str(item).strip()
        ]
        max_hits = invocation.arguments.get("max_hits", 8)
        try:
            max_hits = max(1, min(int(max_hits), 50))
        except (TypeError, ValueError):
            max_hits = 8
        if self._search_fn is None:
            return unavailable(self.name, "retrieval pipeline not bound yet")
        try:
            hits = self._search_fn(query, document_sets, max_hits, ctx)
        except Exception as exc:
            return text_result(f"[rag_search] search failed: {exc}")
        if not hits:
            return text_result("[rag_search] no matching documents")
        lines = []
        for i, hit in enumerate(hits, start=1):
            title = hit.get("title") or hit.get("semantic_identifier") or "(untitled)"
            snippet = (hit.get("blurb") or hit.get("content") or "").strip()
            link = hit.get("link")
            line = f"{i}. {title}"
            if link:
                line += f" ({link})"
            if snippet:
                line += f"\n   {snippet[:500]}"
            lines.append(line)
        return text_result("\n\n".join(lines))


# ── question ──────────────────────────────────────────────────────────────


@dataclass
class QuestionPayload:
    prompt: str
    options: list[str]


QuestionHook = Callable[[ToolInvocation, QuestionPayload, ToolContext], ToolResult]


class QuestionTool:
    name = "question"
    description = (
        "Ask the user a question with selectable options when you need a "
        "decision or missing information. The turn parks until the user "
        "answers."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The question."},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Selectable answers (optional).",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, hook: QuestionHook | None = None) -> None:
        self._hook = hook

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        prompt = str(invocation.arguments.get("prompt", "")).strip()
        if not prompt:
            return text_result("[question] argument 'prompt' is required")
        options = [
            str(item)
            for item in invocation.arguments.get("options", [])
            if str(item).strip()
        ]
        if self._hook is None:
            return unavailable(self.name, "no question hook bound for this session")
        return self._hook(invocation, QuestionPayload(prompt, options), ctx)


# ── background ────────────────────────────────────────────────────────────


@dataclass
class BackgroundRequest:
    action: str
    command: str | None
    process_id: str | None
    stdin: str | None


@dataclass
class BackgroundReply:
    output: str


BackgroundHook = Callable[[ToolInvocation, BackgroundRequest, ToolContext], ToolResult]


class BackgroundTool:
    name = "background"
    description = (
        "Run long shell commands in the sandbox background (builds, "
        "installs, servers) without blocking the turn. Actions: start, "
        "poll, send_input, stop, list."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "poll", "send_input", "stop", "list"],
            },
            "command": {"type": "string", "description": "For action=start."},
            "process_id": {
                "type": "string",
                "description": "For poll/send_input/stop.",
            },
            "stdin": {"type": "string", "description": "For send_input."},
        },
        "required": ["action"],
    }

    def __init__(self, hook: BackgroundHook | None = None) -> None:
        self._hook = hook

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        action = str(invocation.arguments.get("action", "")).strip()
        if not action:
            return text_result("[background] argument 'action' is required")
        request = BackgroundRequest(
            action=action,
            command=invocation.arguments.get("command"),
            process_id=invocation.arguments.get("process_id"),
            stdin=invocation.arguments.get("stdin"),
        )
        if self._hook is None:
            return unavailable(
                self.name, "process data plane not bound for this session"
            )
        return self._hook(invocation, request, ctx)


# ── declared-for-later milestones ─────────────────────────────────────────


class _DeferredTool:
    """Placeholder keeping the schema stable until its milestone binds it."""

    def __init__(self, name: str, description: str, parameters: dict[str, Any], milestone: str) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._milestone = milestone

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        return unavailable(self.name, f"lands with milestone {self._milestone}")


def mcp_call_tool() -> _DeferredTool:
    return _DeferredTool(
        name="mcp_call",
        description=(
            "Call an external MCP tool through the enterprise MCP gateway "
            "(invoices, business registry, pharma databases)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "server": {"type": "string"},
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["server", "tool"],
        },
        milestone="M6 (MCP gateway)",
    )


def web_search_tool() -> _DeferredTool:
    return _DeferredTool(
        name="web_search",
        description="Search the public web for fresh information with citations.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        milestone="M6 (search providers)",
    )


def crawl_tool() -> _DeferredTool:
    return _DeferredTool(
        name="crawl",
        description=(
            "Submit a URL or site to the crawler platform and fetch its "
            "extracted content (async: submit then poll)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "wait": {"type": "boolean"},
            },
            "required": ["url"],
        },
        milestone="M6 (crawler platform)",
    )


def connector_query_tool() -> _DeferredTool:
    return _DeferredTool(
        name="connector_query",
        description=(
            "Query a connected business system (Feishu, WeCom, DingTalk, "
            "WPS365, SAP) through its connector."
        ),
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["source", "query"],
        },
        milestone="M5 (connectors)",
    )
