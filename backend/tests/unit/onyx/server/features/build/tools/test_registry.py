"""Unit tests for the platform tool registry and the stateless MCP server."""

from typing import Any

from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.mcp_server import handle_mcp_jsonrpc
from onyx.server.features.build.tools.registry import (
    PlatformToolRegistry,
    ToolBindings,
    ToolJournalEntry,
)

CTX = ToolContext(user_id="u1")


def _registry_with_search() -> PlatformToolRegistry:
    def fake_search(
        query: str, sets: list[str], limit: int, ctx: ToolContext
    ) -> list[dict[str, Any]]:
        return [
            {"title": "Q3 财务制度", "blurb": f"关于 {query}", "link": "/d/1"},
            {"title": "发票管理规范", "blurb": "…", "link": "/d/2"},
        ][:limit]

    return PlatformToolRegistry.build(ToolBindings(search_fn=fake_search))


def test_catalog_shape_is_stable() -> None:
    registry = PlatformToolRegistry.build(ToolBindings())
    names = set(registry.tools)
    assert names == {
        "rag_search",
        "question",
        "background",
        "mcp_call",
        "web_search",
        "crawl",
        "connector_query",
    }
    defs = registry.definitions()
    assert all(
        {"name", "description", "inputSchema"} <= set(d) for d in defs
    )


def test_rag_search_formats_hits() -> None:
    registry = _registry_with_search()
    result = registry.call(
        ToolInvocation(tool="rag_search", arguments={"query": "报销制度"}), CTX
    )
    text = result.text()
    assert "Q3 财务制度" in text
    assert "/d/1" in text
    assert not result.terminate


def test_rag_search_requires_query() -> None:
    registry = _registry_with_search()
    result = registry.call(ToolInvocation(tool="rag_search", arguments={}), CTX)
    assert "required" in result.text()


def test_unbound_services_report_structured_unavailability() -> None:
    registry = PlatformToolRegistry.build(ToolBindings())
    unbound_args = {
        "rag_search": {"query": "q"},
        "question": {"prompt": "p"},
        "background": {"action": "list"},
        "mcp_call": {"server": "s", "tool": "t"},
    }
    for tool, arguments in unbound_args.items():
        result = registry.call(ToolInvocation(tool=tool, arguments=arguments), CTX)
        assert "unavailable" in result.text(), tool


def test_unknown_tool_lists_known_tools() -> None:
    registry = PlatformToolRegistry.build(ToolBindings())
    result = registry.call(ToolInvocation(tool="bananas", arguments={}), CTX)
    assert "unknown tool" in result.text()
    assert "rag_search" in result.text()


def test_journal_receives_capped_entries() -> None:
    entries: list[ToolJournalEntry] = []
    registry = PlatformToolRegistry.build(
        ToolBindings(
            journal=entries.append,
            search_fn=lambda q, s, l, c: [{"title": "t", "blurb": "x" * 300}],
        )
    )
    registry.call(
        ToolInvocation(tool="rag_search", arguments={"query": "q"}, session_id="s1"),
        CTX,
    )
    assert len(entries) == 1
    assert entries[0].tool == "rag_search"
    assert entries[0].session_id == "s1"
    assert entries[0].ok
    assert len(entries[0].result_text) <= 2000


def test_tool_exception_becomes_error_result_not_crash() -> None:
    def exploding(query: str, sets: list[str], limit: int, ctx: ToolContext) -> list[dict[str, Any]]:
        raise RuntimeError("boom")

    registry = PlatformToolRegistry.build(ToolBindings(search_fn=exploding))
    # rag_search catches its search backend errors and reports them as a
    # tool-level result; the turn must not crash either way.
    result = registry.call(ToolInvocation(tool="rag_search", arguments={"query": "q"}), CTX)
    assert "search failed" in result.text()


def test_mcp_initialize_tools_list_and_call() -> None:
    registry = _registry_with_search()

    init = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        registry,
        CTX,
        None,
    )
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "onyx-platform-tools"

    listing = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        registry,
        CTX,
        None,
    )
    assert listing is not None
    tool_names = {t["name"] for t in listing["result"]["tools"]}
    assert "rag_search" in tool_names

    call = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "rag_search", "arguments": {"query": "发票"}},
        },
        registry,
        CTX,
        "sess-1",
    )
    assert call is not None
    blocks = call["result"]["content"]
    assert blocks and blocks[0]["type"] == "text"
    assert "发票管理规范" in blocks[0]["text"]


def test_mcp_unknown_method_and_notification() -> None:
    registry = PlatformToolRegistry.build(ToolBindings())
    err = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 9, "method": "resources/list", "params": {}},
        registry,
        CTX,
        None,
    )
    assert err is not None
    assert err["error"]["code"] == -32601

    note = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}, registry, CTX, None
    )
    assert note is None
