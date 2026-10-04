"""The crawl tool's content-provider fallback."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from onyx.server.features.build.tools.crawler import (
    ContentProviderCrawler,
    CrawlResult,
    build_content_provider_crawler,
)
from onyx.tools.tool_implementations.open_url.onyx_web_crawler import OnyxWebCrawler
from onyx.tools.tool_implementations.web_search.models import WebContentProviderConfig


def _provider(contents_result: list, error: Exception | None = None) -> SimpleNamespace:
    def contents(_urls: list[str]) -> list:
        if error is not None:
            raise error
        return contents_result

    return SimpleNamespace(contents=contents)


def test_content_provider_crawler_sync_returns_content() -> None:
    crawler = ContentProviderCrawler(
        _provider(
            [
                SimpleNamespace(
                    title="Example",
                    link="https://example.com",
                    full_content="hello world",
                    scrape_successful=True,
                    failure_reason=None,
                )
            ]
        )
    )
    result = crawler.crawl_sync("https://example.com")
    assert isinstance(result, CrawlResult)
    assert result.status == "done"
    assert result.content == "hello world"


def test_content_provider_crawler_reports_failure() -> None:
    crawler = ContentProviderCrawler(
        _provider(
            [
                SimpleNamespace(
                    title="",
                    link="https://example.com",
                    full_content="",
                    scrape_successful=False,
                    failure_reason="blocked by a bot challenge",
                )
            ]
        )
    )
    result = crawler.crawl_sync("https://example.com")
    assert result.status == "failed"
    assert "bot challenge" in (result.error or "")


def test_content_provider_crawler_submit_poll_roundtrip() -> None:
    crawler = ContentProviderCrawler(
        _provider(
            [
                SimpleNamespace(
                    title="Example",
                    link="https://example.com",
                    full_content="content",
                    scrape_successful=True,
                    failure_reason=None,
                )
            ]
        )
    )
    job_id = crawler.submit("https://example.com")
    final: CrawlResult | None = None
    for _ in range(50):
        final = crawler.poll(job_id)
        if final.status != "running":
            break
    assert final is not None and final.status == "done"
    assert final.content == "content"
    # Job records are consumed: polling again reports unknown.
    assert crawler.poll(job_id).status == "failed"


def _patch_provider_row(
    monkeypatch: pytest.MonkeyPatch, row: SimpleNamespace | None
) -> None:
    """Stub the DB lookups build_content_provider_crawler performs."""

    @contextmanager
    def fake_session() -> Iterator[None]:
        yield None

    def fake_fetch(_db_session: None) -> SimpleNamespace | None:
        return row

    import onyx.db.engine.sql_engine as sql_engine
    import onyx.db.web_search as db_web_search

    monkeypatch.setattr(sql_engine, "get_session_with_current_tenant", fake_session)
    monkeypatch.setattr(db_web_search, "fetch_active_web_content_provider", fake_fetch)


def _provider_row(
    provider_type: str,
    api_key: SimpleNamespace | None,
    config: WebContentProviderConfig | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=f"row-{provider_type}",
        provider_type=provider_type,
        api_key=api_key,
        config=config,
    )


def test_build_defaults_to_builtin_crawler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No configured provider: the built-in crawler serves the tool, like chat."""
    _patch_provider_row(monkeypatch, None)
    crawler = build_content_provider_crawler()
    assert isinstance(crawler, ContentProviderCrawler)
    assert isinstance(crawler._provider, OnyxWebCrawler)


def test_build_misconfigured_firecrawl_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Firecrawl row without a base URL degrades instead of raising."""
    key = SimpleNamespace(get_value=lambda *_args, **_kwargs: "fc-test")
    _patch_provider_row(
        monkeypatch, _provider_row("firecrawl", key, WebContentProviderConfig())
    )
    assert build_content_provider_crawler() is None


def test_build_external_row_without_key_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_provider_row(monkeypatch, _provider_row("exa", None, None))
    assert build_content_provider_crawler() is None


def test_build_builtin_row_without_key_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The built-in crawler type needs no API key."""
    _patch_provider_row(
        monkeypatch, _provider_row("onyx_web_crawler", None, WebContentProviderConfig())
    )
    crawler = build_content_provider_crawler()
    assert isinstance(crawler, ContentProviderCrawler)
    assert isinstance(crawler._provider, OnyxWebCrawler)
