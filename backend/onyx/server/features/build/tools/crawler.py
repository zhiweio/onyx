"""Crawler platform client: async submit → poll extracted content.

Works with any crawler service exposing the two-call contract
(Crawl4AI server, or the enterprise crawler platform):

- ``POST {base}/crawl`` {url} → {job_id}
- ``GET {base}/crawl/{job_id}`` → {status, content|error}

``CRAWLER_BASE_URL`` configures the endpoint. When it is empty, the crawl
tool is served from the admin-configured web content provider instead
(``build_content_provider_crawler``): Firecrawl, OnyxWebCrawler, Exa or
Tavily — the same provider chat's open-url uses, with the same built-in
fallback when nothing is configured.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import requests

from onyx.tools.tool_implementations.open_url.models import WebContent
from onyx.utils.logger import setup_logger

logger = setup_logger()

CRAWLER_BASE_ENV = "CRAWLER_BASE_URL"
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_WAIT_SECONDS = 60.0


class CrawlerError(Exception):
    """Crawler refused the job or the wait timed out."""


@dataclass(frozen=True)
class CrawlResult:
    url: str
    status: str
    content: str = ""
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.status in ("done", "completed", "failed", "error")


class CrawlerClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        max_wait: float = DEFAULT_MAX_WAIT_SECONDS,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._poll_interval = poll_interval
        self._max_wait = max_wait

    def submit(self, url: str) -> str:
        resp = self._session.post(f"{self._base}/crawl", json={"url": url}, timeout=30)
        if resp.status_code != 200:
            raise CrawlerError(f"submit failed: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        job_id = data.get("job_id") or data.get("id")
        if not job_id:
            raise CrawlerError(f"crawler returned no job id: {data}")
        return str(job_id)

    def poll(self, job_id: str) -> CrawlResult:
        resp = self._session.get(f"{self._base}/crawl/{job_id}", timeout=30)
        if resp.status_code != 200:
            raise CrawlerError(f"poll failed: HTTP {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return CrawlResult(
            url=str(data.get("url") or ""),
            status=str(data.get("status") or "unknown"),
            content=str(data.get("content") or data.get("markdown") or ""),
            error=(str(data["error"]) if data.get("error") else None),
        )

    def crawl_sync(self, url: str) -> CrawlResult:
        """Submit and wait (bounded) for the extracted content."""
        job_id = self.submit(url)
        deadline = time.time() + self._max_wait
        while time.time() < deadline:
            result = self.poll(job_id)
            if result.done:
                return result
            time.sleep(self._poll_interval)
        raise CrawlerError(f"crawl of {url} did not finish in {self._max_wait}s")


def build_crawler_client() -> CrawlerClient | None:
    """The configured crawler, or None when unconfigured."""
    base = os.environ.get(CRAWLER_BASE_ENV, "").strip()
    if not base:
        return None
    return CrawlerClient(base, api_key=os.environ.get("CRAWLER_API_KEY") or None)


class ContentProviderCrawler:
    """Adapts the admin-configured web content provider to the crawl tool.

    When no ``CRAWLER_BASE_URL`` service is deployed, the crawl tool falls
    back to the provider an administrator configured under web content
    providers (Firecrawl, the built-in OnyxWebCrawler, Exa, Tavily).
    ``submit``/``poll`` run the fetch on a worker thread so the two-call
    contract holds in-process; ``crawl_sync`` blocks on the result.
    """

    _MAX_WORKERS = 4

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self._pool = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)
        self._futures: dict[str, tuple[str, Future]] = {}
        self._lock = threading.Lock()

    def submit(self, url: str) -> str:
        job_id = uuid.uuid4().hex
        future = self._pool.submit(self._provider.contents, [url])
        with self._lock:
            self._futures[job_id] = (url, future)
        return job_id

    def poll(self, job_id: str) -> CrawlResult:
        with self._lock:
            entry = self._futures.get(job_id)
        if entry is None:
            return CrawlResult(url="", status="failed", error="unknown job")
        url, future = entry
        if not future.done():
            return CrawlResult(url=url, status="running")
        with self._lock:
            self._futures.pop(job_id, None)
        try:
            contents = future.result()
            return CrawlResult(
                url=url, status="done", content=self._content_of(contents[0])
            )
        except Exception as exc:
            return CrawlResult(url=url, status="failed", error=str(exc))

    def crawl_sync(self, url: str) -> CrawlResult:
        try:
            contents = self._provider.contents([url])
            return CrawlResult(
                url=url, status="done", content=self._content_of(contents[0])
            )
        except Exception as exc:
            return CrawlResult(url=url, status="failed", error=str(exc))

    def _content_of(self, web_content: WebContent) -> str:
        if not web_content.scrape_successful:
            raise RuntimeError(web_content.failure_reason or "scrape failed")
        if not web_content.full_content:
            raise RuntimeError("crawler returned empty content")
        return web_content.full_content


def build_content_provider_crawler() -> ContentProviderCrawler | None:
    """Crawler backed by the admin-configured web content provider.

    Mirrors the chat-side resolution in ``features/web_search/api.py``:
    the active provider row is built from its stored key and config, and
    when nothing is configured the built-in ``OnyxWebCrawler`` serves the
    tool, so one admin setting covers chat and craft. A broken row
    degrades to ``None`` (crawl tool unavailable) instead of raising —
    this runs inside the tool-bridge registry build.
    """
    from onyx.db.engine.sql_engine import get_session_with_current_tenant
    from onyx.db.web_search import fetch_active_web_content_provider
    from onyx.tools.tool_implementations.open_url.onyx_web_crawler import (
        DEFAULT_MAX_HTML_SIZE_BYTES,
        DEFAULT_MAX_PDF_SIZE_BYTES,
        OnyxWebCrawler,
    )
    from onyx.tools.tool_implementations.web_search.models import (
        WebContentProviderConfig,
    )
    from onyx.tools.tool_implementations.web_search.providers import (
        build_content_provider_from_config,
    )
    from shared_configs.enums import WebContentProviderType

    with get_session_with_current_tenant() as db_session:
        provider_model = fetch_active_web_content_provider(db_session)

    if provider_model is None:
        # Chat's open-url default: the built-in crawler is always available.
        return ContentProviderCrawler(
            OnyxWebCrawler(
                max_pdf_size_bytes=DEFAULT_MAX_PDF_SIZE_BYTES,
                max_html_size_bytes=DEFAULT_MAX_HTML_SIZE_BYTES,
            )
        )

    api_key = (
        provider_model.api_key.get_value(apply_mask=False)
        if provider_model.api_key
        else None
    )
    is_builtin = (
        provider_model.provider_type == WebContentProviderType.ONYX_WEB_CRAWLER.value
    )
    if is_builtin:
        # The builder ignores the key for the built-in crawler type.
        api_key = api_key or ""
    elif api_key is None:
        logger.warning(
            "Active web content provider '%s' has no API key; crawl tool unavailable",
            provider_model.name,
        )
        return None

    try:
        provider = build_content_provider_from_config(
            provider_type=WebContentProviderType(provider_model.provider_type),
            api_key=api_key,
            config=provider_model.config or WebContentProviderConfig(),
        )
    except ValueError as exc:
        logger.warning(
            "Active web content provider '%s' is misconfigured (%s); "
            "crawl tool unavailable",
            provider_model.name,
            exc,
        )
        return None
    if provider is None:
        return None
    return ContentProviderCrawler(provider)
