"""The crawl tool's content-provider fallback."""

from __future__ import annotations

from types import SimpleNamespace

from onyx.server.features.build.tools.crawler import (
    ContentProviderCrawler,
    CrawlResult,
)


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
