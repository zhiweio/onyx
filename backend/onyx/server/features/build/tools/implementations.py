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


# ── mcp_call (enterprise MCP gateway) ─────────────────────────────────────


McpCallFn = Callable[[str, str, dict[str, Any]], str]


class McpCallTool:
    name = "mcp_call"
    description = (
        "Call an external MCP tool through the enterprise MCP gateway "
        "(invoices, business registry, pharma databases). Only servers "
        "granted for the current task are reachable."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "Gateway server name."},
            "tool": {"type": "string", "description": "Tool name on that server."},
            "arguments": {
                "type": "object",
                "description": "Tool arguments.",
            },
        },
        "required": ["server", "tool"],
    }

    def __init__(self, call_fn: McpCallFn | None = None) -> None:
        self._call_fn = call_fn

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        server = str(invocation.arguments.get("server", "")).strip()
        tool = str(invocation.arguments.get("tool", "")).strip()
        if not server or not tool:
            return text_result("[mcp_call] 'server' and 'tool' are required")
        arguments = invocation.arguments.get("arguments") or {}
        if not isinstance(arguments, dict):
            return text_result("[mcp_call] 'arguments' must be an object")
        if self._call_fn is None:
            return unavailable(self.name, "no MCP gateway configured")
        try:
            reply = self._call_fn(server, tool, arguments)
        except Exception as exc:
            return text_result(f"[mcp_call] gateway error: {exc}")
        return text_result(reply)


# ── web_search (pluggable providers) ──────────────────────────────────────


WebSearchFn = Callable[[str, int], str]


class WebSearchTool:
    name = "web_search"
    description = (
        "Search the public web through the configured provider "
        "(Bocha/Baidu/SearXNG). Returns titled results with URLs and "
        "snippets."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
    }

    def __init__(self, search_fn: WebSearchFn | None = None) -> None:
        self._search_fn = search_fn

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        query = str(invocation.arguments.get("query", "")).strip()
        if not query:
            return text_result("[web_search] argument 'query' is required")
        max_results = invocation.arguments.get("max_results", 8)
        try:
            max_results = max(1, min(int(max_results), 20))
        except (TypeError, ValueError):
            max_results = 8
        if self._search_fn is None:
            return unavailable(self.name, "no search provider configured")
        try:
            return text_result(self._search_fn(query, max_results))
        except Exception as exc:
            return text_result(f"[web_search] search failed: {exc}")


# ── crawl (crawler platform) ──────────────────────────────────────────────


CrawlFn = Callable[[str, bool], str]


class CrawlTool:
    name = "crawl"
    description = (
        "Crawl a URL through the crawler platform and return its extracted "
        "text. wait=true blocks until extraction finishes (bounded)."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "wait": {"type": "boolean", "description": "Wait for content."},
        },
        "required": ["url"],
    }

    def __init__(self, crawl_fn: CrawlFn | None = None) -> None:
        self._crawl_fn = crawl_fn

    def execute(self, invocation: ToolInvocation, ctx: ToolContext) -> ToolResult:
        url = str(invocation.arguments.get("url", "")).strip()
        if not url:
            return text_result("[crawl] argument 'url' is required")
        wait = bool(invocation.arguments.get("wait", True))
        if self._crawl_fn is None:
            return unavailable(self.name, "no crawler platform configured")
        try:
            return text_result(self._crawl_fn(url, wait))
        except Exception as exc:
            return text_result(f"[crawl] crawl failed: {exc}")


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


def mcp_call_tool(call_fn: McpCallFn | None = None) -> McpCallTool:
    return McpCallTool(call_fn)


def web_search_tool(search_fn: WebSearchFn | None = None) -> WebSearchTool:
    return WebSearchTool(search_fn)


def crawl_tool(crawl_fn: CrawlFn | None = None) -> CrawlTool:
    return CrawlTool(crawl_fn)


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
