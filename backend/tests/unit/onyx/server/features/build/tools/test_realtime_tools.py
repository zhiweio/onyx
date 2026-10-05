"""Unit tests for M6: search providers, crawler, tool wiring."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from requests_mock import Mocker as RequestsMocker

from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.crawler import (
    CrawlerClient,
    CrawlerError,
)
from onyx.server.features.build.tools.implementations import (
    WebSearchTool,
)
from onyx.server.features.build.tools.registry import (
    PlatformToolRegistry,
    ToolBindings,
)
from onyx.server.features.build.tools.web_search_providers import (
    AdminSearchProvider,
    SearXNGSearchProvider,
    build_configured_search_provider,
    build_search_provider,
    format_hits,
)
from onyx.tools.tool_implementations.web_search.models import WebSearchResult

CTX = ToolContext(user_id="u1")


# ── MCP gateway ───────────────────────────────────────────────────────────


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


def _patch_admin_search_row(
    monkeypatch: pytest.MonkeyPatch, row: SimpleNamespace | None
) -> None:
    """Stub the DB lookups build_configured_search_provider performs."""

    @contextmanager
    def fake_session() -> Iterator[None]:
        yield None

    def fake_fetch(_db_session: Any) -> SimpleNamespace | None:
        return row

    import onyx.db.engine.sql_engine as sql_engine
    import onyx.db.web_search as db_web_search

    monkeypatch.setattr(sql_engine, "get_session_with_current_tenant", fake_session)
    monkeypatch.setattr(db_web_search, "fetch_active_web_search_provider", fake_fetch)


def test_configured_search_provider_prefers_admin_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin panel row wins, like chat's web search."""
    _patch_admin_search_row(
        monkeypatch,
        SimpleNamespace(
            name="本地 SearXNG",
            provider_type="searxng",
            api_key=None,
            config={"searxng_base_url": "http://searxng:8080"},
        ),
    )
    provider = build_configured_search_provider()
    assert provider is not None
    assert provider.name == "searxng"


def test_configured_search_provider_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No admin row: the env channel keeps serving deployments without one."""
    _patch_admin_search_row(monkeypatch, None)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://x:8080")
    provider = build_configured_search_provider()
    assert provider is not None
    assert provider.name == "searxng"


def test_configured_search_provider_broken_row_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misconfigured row degrades with a warning instead of raising."""
    _patch_admin_search_row(
        monkeypatch,
        SimpleNamespace(
            name="broken", provider_type="searxng", api_key=None, config={}
        ),
    )
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    assert build_configured_search_provider() is None


def test_admin_search_provider_adapts_chat_results() -> None:
    chat_provider = SimpleNamespace(
        search=lambda _query: [
            WebSearchResult(
                title="公告",
                link="https://gov.example/notice",
                snippet="x" * 500,
                published_date=datetime(2026, 3, 1, 12, 0),
            ),
            WebSearchResult(title="第二条", link="https://gov.example/2", snippet="s"),
        ]
    )
    adapter = AdminSearchProvider("searxng", chat_provider)
    hits = adapter.search("增值税", max_results=1)
    assert len(hits) == 1
    assert hits[0].title == "公告"
    assert hits[0].url == "https://gov.example/notice"
    assert hits[0].published == "2026-03-01"
    assert len(hits[0].snippet) == 401 and hits[0].snippet.endswith("…")


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
            web_search_fn=lambda q, _n: f"search:{q}",
            crawl_fn=lambda u, _w: f"crawl:{u}",
        )
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
