"""Unit tests for M6: MCP gateway, search providers, crawler, tool wiring."""

from typing import Any

import pytest
from requests_mock import Mocker as RequestsMocker

from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.crawler import (
    CrawlerClient,
    CrawlerError,
)
from onyx.server.features.build.tools.implementations import (
    McpCallTool,
    WebSearchTool,
)
from onyx.server.features.build.tools.mcp_gateway import (
    GatewayServerConfig,
    McpGatewayError,
    McpGatewayService,
    load_gateway_servers,
)
from onyx.server.features.build.tools.registry import (
    PlatformToolRegistry,
    ToolBindings,
)
from onyx.server.features.build.tools.web_search_providers import (
    SearXNGSearchProvider,
    build_search_provider,
    format_hits,
)

CTX = ToolContext(user_id="u1")


# ── MCP gateway ───────────────────────────────────────────────────────────


def test_gateway_config_parsing() -> None:
    raw = '[{"name": "invoice", "url": "https://mcp.example/mcp", "headers": {"X-K": "v"}}, {"bad": 1}]'
    servers = load_gateway_servers(raw)
    assert set(servers) == {"invoice"}
    assert servers["invoice"].url == "https://mcp.example/mcp"
    assert servers["invoice"].headers == {"X-K": "v"}
    assert load_gateway_servers("") == {}
    with pytest.raises(McpGatewayError):
        load_gateway_servers("not json")


def test_gateway_allowlist_and_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    async def fake_call(
        _self: McpGatewayService, config: Any, tool: str, _args: dict[str, Any]
    ) -> str:
        return f"upstream:{config.name}:{tool}"

    monkeypatch.setattr(McpGatewayService, "_call_upstream", fake_call)

    service = McpGatewayService(
        {"invoice": GatewayServerConfig(name="invoice", url="https://x")},
        audit=calls.append,
    )

    # allowed
    out = service.call_tool_sync(
        server="invoice", tool="check", arguments={}, user_id="u1"
    )
    assert out == "upstream:invoice:check"
    assert calls[-1].ok is True

    # not granted
    with pytest.raises(McpGatewayError, match="not granted"):
        service.call_tool_sync(
            server="invoice",
            tool="check",
            arguments={},
            user_id="u1",
            allowed_servers=set(),
        )

    # unknown server
    with pytest.raises(McpGatewayError, match="unknown"):
        service.call_tool_sync(server="nope", tool="t", arguments={}, user_id="u1")

    # upstream failure is journaled as not ok
    async def boom(
        _self: McpGatewayService,
        _config: Any,
        _tool: str,
        _args: dict[str, Any],
    ) -> str:
        raise RuntimeError("upstream down")

    monkeypatch.setattr(McpGatewayService, "_call_upstream", boom)
    with pytest.raises(RuntimeError):
        service.call_tool_sync(
            server="invoice", tool="check", arguments={}, user_id="u1"
        )
    assert calls[-1].ok is False
    assert calls[-1].error == "upstream down"


def test_mcp_call_tool_requires_and_degrades() -> None:
    unbound = McpCallTool()
    result = unbound.execute(
        ToolInvocation(tool="mcp_call", arguments={"server": "s", "tool": "t"}), CTX
    )
    assert "unavailable" in result.text()

    missing = McpCallTool(lambda _s, _t, _a: "ok").execute(
        ToolInvocation(tool="mcp_call", arguments={}), CTX
    )
    assert "required" in missing.text()

    failing = McpCallTool(
        lambda _s, _t, _a: (_ for _ in ()).throw(RuntimeError("x"))
    ).execute(
        ToolInvocation(tool="mcp_call", arguments={"server": "s", "tool": "t"}), CTX
    )
    assert "gateway error" in failing.text()


# ── search providers ──────────────────────────────────────────────────────


def test_searxng_provider_parses_and_formats(requests_mock: RequestsMocker) -> None:
    requests_mock.get(
        "https://searx.example/search",
        json={
            "results": [
                {
                    "title": "税务总局公告",
                    "url": "https://gov.example/notice",
                    "content": "2026年增值税新政要点",
                    "publishedDate": "2026-03-01",
                }
            ]
        },
    )
    provider = SearXNGSearchProvider("https://searx.example")
    hits = provider.search("增值税", max_results=5)
    assert len(hits) == 1
    assert hits[0].published == "2026-03-01"

    text = format_hits("增值税", hits)
    assert "gov.example/notice" in text
    assert "2026-03-01" in text
    assert format_hits("增值税", []) == "[web_search] no results for '增值税'"


def test_build_search_provider_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_search_provider(None) is None
    assert build_search_provider("unknown") is None
    monkeypatch.setenv("BOCHA_API_KEY", "")
    assert build_search_provider("bocha") is None
    monkeypatch.setenv("BOCHA_API_KEY", "k")
    assert build_search_provider("bocha") is not None
    assert build_search_provider("searxng", searxng_url="http://x") is not None


def test_web_search_tool_formats_via_injected_fn() -> None:
    tool = WebSearchTool(lambda q, n: f"hits for {q} x{n}")
    result = tool.execute(
        ToolInvocation(tool="web_search", arguments={"query": "增值税新政"}), CTX
    )
    assert "hits for 增值税新政" in result.text()

    unbound = WebSearchTool()
    assert (
        "unavailable"
        in unbound.execute(
            ToolInvocation(tool="web_search", arguments={"query": "q"}), CTX
        ).text()
    )


# ── crawler ───────────────────────────────────────────────────────────────


def test_crawler_submit_poll_sync(requests_mock: RequestsMocker) -> None:
    client = CrawlerClient("http://crawler.example", poll_interval=0.01, max_wait=5)
    requests_mock.post("http://crawler.example/crawl", json={"job_id": "j1"})
    requests_mock.get(
        "http://crawler.example/crawl/j1",
        [
            {"json": {"status": "running"}},
            {
                "json": {
                    "status": "done",
                    "content": "公告全文…",
                    "url": "https://gov/1",
                }
            },
        ],
    )
    result = client.crawl_sync("https://gov/1")
    assert result.done
    assert "公告全文" in result.content


def test_crawler_timeout_raises(requests_mock: RequestsMocker) -> None:
    client = CrawlerClient("http://crawler.example", poll_interval=0.01, max_wait=0.05)
    requests_mock.post("http://crawler.example/crawl", json={"job_id": "j1"})
    requests_mock.get("http://crawler.example/crawl/j1", json={"status": "running"})
    with pytest.raises(CrawlerError, match="did not finish"):
        client.crawl_sync("https://x")


# ── registry end-to-end with all bindings ────────────────────────────────


def test_registry_runs_bound_realtime_tools() -> None:
    registry = PlatformToolRegistry.build(
        ToolBindings(
            mcp_call_fn=lambda s, t, _a: f"mcp:{s}/{t}",
            web_search_fn=lambda q, _n: f"search:{q}",
            crawl_fn=lambda u, _w: f"crawl:{u}",
        )
    )
    assert (
        registry.call(
            ToolInvocation(
                tool="mcp_call",
                arguments={"server": "invoice", "tool": "check", "arguments": {}},
            ),
            CTX,
        ).text()
        == "mcp:invoice/check"
    )
    assert (
        registry.call(
            ToolInvocation(tool="web_search", arguments={"query": "q"}), CTX
        ).text()
        == "search:q"
    )
    assert (
        registry.call(
            ToolInvocation(tool="crawl", arguments={"url": "https://x"}), CTX
        ).text()
        == "crawl:https://x"
    )
